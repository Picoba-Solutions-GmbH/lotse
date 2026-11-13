"""Deploys package versions from container image tags (like Argo CD Image Updater).

- check(): looks for new semver tags of an image and, with auto sync, deploys the newest one
- sync():  deploys the newest or a given tag
- discover(): lists the images below the path of a registry and registers new ones as image sources

Versions are pinned to the image digest, so a version always runs exactly the image it was deployed with.
"""
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime

import yaml
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import SYSTEM_ADMIN, SYSTEM_USER_ID
from src.database.database_access import SessionLocal
from src.database.models.image_source_entity import ImageSourceEntity
from src.database.models.registry_entity import RegistryEntity
from src.database.repositories.git_source_repository import \
    GitSourceRepository
from src.database.repositories.image_source_repository import \
    ImageSourceRepository
from src.database.repositories.package_repository import PackageRepository
from src.database.repositories.package_share_repository import \
    PackageShareRepository
from src.database.repositories.registry_repository import RegistryRepository
from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import parse_config
from src.services import package_deploy_service as deployment
from src.services.registry import image_ref, registry_credentials
from src.services.registry.image_package_config import build_image_config
from src.services.registry.registry_client import (ImageNotFoundError,
                                                   RegistryClient,
                                                   RegistryError)
from src.services.sync import common
from src.services.sync.common import (SourceBusyError, SyncConfigError,
                                      describe_error)
from src.services.sync.versions import (TagVersion, is_newer, parse_versions,
                                        version_of)

logger = logging.getLogger(__name__)


@dataclass
class ImageSyncResult:
    # "deployed": a new version was created, "activated": an existing version became the default
    action: str
    tag: str
    version: str
    digest: str


# ---------------------------------------------------------------- helpers

def client_for(registry: RegistryEntity) -> RegistryClient:
    credentials = registry_credentials.read(registry.credential_secret, registry.host)  # type: ignore
    return RegistryClient(registry.host, credentials, registry.provider, registry.api_url)  # type: ignore


def image_name(registry: RegistryEntity, repository: str) -> str:
    return f"{image_ref.normalize_host(registry.host)}/{repository}"  # type: ignore


def _registry_of(db: Session, source: ImageSourceEntity) -> RegistryEntity:
    registry = RegistryRepository.get(db, source.registry_id)  # type: ignore
    if registry is None:
        raise RuntimeError("The registry of this image source was deleted")
    return registry


def list_versions(db: Session, source: ImageSourceEntity) -> list[TagVersion]:
    """Semver tags of the image, newest first. Digests are not resolved ("")."""
    tags = client_for(_registry_of(db, source)).list_tags(source.repository)  # type: ignore
    return parse_versions({tag: "" for tag in tags}, source.tag_prefix)  # type: ignore


def compute_status(source: ImageSourceEntity, active_version: str | None) -> str:
    return common.compute_status(source.last_checked_at, source.last_error, source.latest_tag,  # type: ignore
                                 source.tag_prefix, active_version)  # type: ignore


def pin_image_digest(db: Session, config_text: str) -> str:
    """For a container package from Git: makes sure the image exists and pins it to its digest.

    A missing image is a temporary error (CI may not have pushed it yet), so the sync is retried."""
    package_config = parse_config(config_text)
    if package_config.runtime != RuntimeType.CONTAINER or not package_config.image:
        return config_text
    ref = image_ref.parse(package_config.image)
    if ref.digest:
        return config_text

    registry = RegistryRepository.find_for_image(db, package_config.image)
    client = client_for(registry) if registry else RegistryClient(ref.host)
    try:
        digest = client.resolve_digest(ref.repository, ref.tag or "latest")
    except ImageNotFoundError:
        raise RegistryError(f"Image {package_config.image} doesn't exist (yet). Lotse retries on the next check.")
    except RegistryError as e:
        if registry is not None:
            raise
        # unknown registry, the cluster may still be able to pull it
        logger.info("Can't check image %s without registry credentials: %s", package_config.image, e)
        return config_text

    data = yaml.safe_load(config_text)
    data["image"] = ref.with_digest(digest)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


# ---------------------------------------------------------------- check / sync

def check(source_id: str) -> None:
    """Refreshes the latest tag and deploys it if auto sync is on. Errors end up in last_error."""
    with common.source_lock(source_id) as acquired:
        if not acquired:
            raise SourceBusyError()
        db = SessionLocal()
        try:
            source = ImageSourceRepository.get(db, source_id)
            if source is not None:
                _check_locked(db, source)
        finally:
            db.close()


def sync(source_id: str, tag: str | None = None) -> ImageSyncResult:
    with common.source_lock(source_id) as acquired:
        if not acquired:
            raise SourceBusyError()
        db = SessionLocal()
        try:
            source = ImageSourceRepository.get(db, source_id)
            if source is None:
                raise LookupError("Image source not found")
            try:
                versions = list_versions(db, source)
                target = _pick(source, versions, tag)
                target = _with_digest(db, source, target)
            except Exception as e:
                _record_failure(db, source, e, digest=None)
                raise
            _record_latest(db, source, versions)
            return _sync_locked(db, source, target)
        finally:
            db.close()


def _pick(source: ImageSourceEntity, versions: list[TagVersion], tag: str | None) -> TagVersion:
    if tag is None:
        if not versions:
            raise LookupError(f"The image has no tags matching '{source.tag_prefix}<version>'")
        return versions[0]
    target = next((v for v in versions if v.tag == tag), None)
    if target is None:
        raise LookupError(f"Tag '{tag}' doesn't exist or doesn't match '{source.tag_prefix}<version>'")
    return target


def _with_digest(db: Session, source: ImageSourceEntity, target: TagVersion) -> TagVersion:
    digest = client_for(_registry_of(db, source)).resolve_digest(source.repository, target.tag)  # type: ignore
    return TagVersion(tag=target.tag, version=target.version, commit=digest)


def _record_latest(db: Session, source: ImageSourceEntity, versions: list[TagVersion],
                   latest_digest: str | None = None) -> None:
    latest = versions[0] if versions else None
    source.latest_tag = latest.tag if latest else None  # type: ignore
    if latest_digest is not None or latest is None:
        source.latest_digest = latest_digest  # type: ignore
    source.last_checked_at = datetime.now()  # type: ignore
    if latest_digest is None or latest_digest != source.last_failed_digest:
        source.last_error = None  # type: ignore
    db.commit()


def _record_failure(db: Session, source: ImageSourceEntity, error: Exception, digest: str | None) -> None:
    db.rollback()
    source.last_checked_at = datetime.now()  # type: ignore
    source.last_error = describe_error(error)  # type: ignore
    if digest and common.is_permanent(error):
        source.last_failed_digest = digest  # type: ignore
    db.commit()


def _check_locked(db: Session, source: ImageSourceEntity) -> None:
    try:
        versions = list_versions(db, source)
        latest = _with_digest(db, source, versions[0]) if versions else None
    except Exception as e:
        logger.warning("Checking image source of %s failed: %s", source.package_name, e)
        _record_failure(db, source, e, digest=None)
        return

    _record_latest(db, source, versions, latest.commit if latest else None)
    if not source.auto_sync or latest is None or latest.commit == source.last_failed_digest:
        return
    last_synced_version = version_of(source.last_synced_tag, source.tag_prefix)  # type: ignore
    if not is_newer(latest.version, last_synced_version):
        return

    try:
        result = _sync_locked(db, source, latest)
        logger.info("Image sync deployed %s %s (%s)", source.package_name, result.version, result.digest)
    except Exception as e:
        logger.warning("Image sync of %s %s failed: %s", source.package_name, latest.tag, describe_error(e))


def _sync_locked(db: Session, source: ImageSourceEntity, target: TagVersion) -> ImageSyncResult:
    try:
        result = _deploy_tag(db, source, target)
    except Exception as e:
        _record_failure(db, source, e, digest=target.commit)
        raise

    # the newest tag ever synced: deploying an older tag (roll back) must not make auto sync
    # deploy the newer ones again
    if is_newer(target.version, version_of(source.last_synced_tag, source.tag_prefix)):  # type: ignore
        source.last_synced_tag = target.tag  # type: ignore
        source.last_synced_digest = target.commit  # type: ignore
    source.last_synced_at = datetime.now()  # type: ignore
    source.last_error = None  # type: ignore
    source.last_failed_digest = None  # type: ignore
    db.commit()
    return result


def _deploy_tag(db: Session, source: ImageSourceEntity, target: TagVersion) -> ImageSyncResult:
    package_name: str = source.package_name  # type: ignore
    digest = target.commit
    existing = PackageRepository.get_package(db, package_name, target.version)
    if existing is not None:
        if existing.source_id == source.id and existing.source_commit == digest:
            PackageRepository.set_active_package(db, package_name, target.version)
            return ImageSyncResult(action="activated", tag=target.tag, version=target.version, digest=digest)
        origin = (f"from image {str(existing.source_commit)[:19]}" if existing.source_commit
                  else "by an upload")
        raise SyncConfigError(
            f"Version {target.version} already exists (deployed {origin}). "
            f"Push a new tag, or delete version {target.version} in Lotse to deploy this image.")

    registry = _registry_of(db, source)
    image = f"{image_name(registry, source.repository)}:{target.tag}@{digest}"  # type: ignore
    previous = PackageRepository.get_package(db, package_name)
    config_text = build_image_config(previous.config if previous else None,  # type: ignore
                                     package_name, target.version, image)
    deployment.deploy_package(
        db, SYSTEM_ADMIN, config_text, lambda *_: None,
        set_active=True, delete_previous_versions=bool(source.prune_previous),
        source=deployment.DeploymentSource(type="image", source_id=source.id,  # type: ignore
                                           ref=target.tag, commit=digest),
    )
    return ImageSyncResult(action="deployed", tag=target.tag, version=target.version, digest=digest)


def check_in_background(source_id: str) -> None:
    def run() -> None:
        try:
            check(source_id)
        except SourceBusyError:
            pass
        except Exception:
            logger.exception("Checking image source %s failed", source_id)

    threading.Thread(target=run, daemon=True, name=f"image-check-{source_id[:8]}").start()


# ---------------------------------------------------------------- discovery

def package_name_for(repository: str) -> str:
    """lotse/order-service -> order-service"""
    return repository.rstrip("/").rsplit("/", 1)[-1]


def create_source(db: Session, registry: RegistryEntity, repository: str, package_name: str,
                  created_by: str | None, auto_sync: bool, tag_prefix: str = "",
                  prune_previous: bool = False, poll_interval_seconds: int = 120) -> ImageSourceEntity:
    source = ImageSourceEntity(
        id=str(uuid.uuid4()),
        package_name=package_name,
        registry_id=registry.id,
        repository=image_ref.normalize_repository(registry.host, repository),  # type: ignore
        tag_prefix=tag_prefix,
        auto_sync=auto_sync,
        prune_previous=prune_previous,
        poll_interval_seconds=poll_interval_seconds,
        webhook_token=secrets.token_urlsafe(24),
        created_by=created_by,
        created_at=datetime.now(),
    )
    return ImageSourceRepository.create(db, source)


def name_taken(db: Session, package_name: str) -> bool:
    return (ImageSourceRepository.get_by_package(db, package_name) is not None
            or GitSourceRepository.get_by_package(db, package_name) is not None)


def discover(registry_id: str) -> list[str]:
    """Registers new images below the discovery path. Returns the package names it created."""
    with common.source_lock(f"registry-{registry_id}") as acquired:
        if not acquired:
            raise SourceBusyError()
        db = SessionLocal()
        try:
            registry = RegistryRepository.get(db, registry_id)
            if registry is None or registry.discovery_path is None:
                return []
            try:
                repositories = client_for(registry).list_repositories(registry.discovery_path)  # type: ignore
            except Exception as e:
                db.rollback()
                registry.last_discovered_at = datetime.now()  # type: ignore
                registry.last_error = describe_error(e)  # type: ignore
                db.commit()
                raise

            registered = {str(s.repository) for s in ImageSourceRepository.list_all(db, registry_id=registry_id)}
            created: list[str] = []
            skipped: list[str] = []
            for repository in repositories:
                if repository in registered:
                    continue
                name = package_name_for(repository)
                if name_taken(db, name):
                    skipped.append(f"{repository} (package {name} is already connected)")
                    continue
                source = create_source(db, registry, repository, name, registry.created_by,  # type: ignore
                                       auto_sync=bool(registry.default_auto_sync))
                owner = registry.created_by
                if owner and owner != SYSTEM_USER_ID and not PackageRepository.list_packages(db, name) \
                        and PackageShareRepository.get_owner_id(db, name) is None:
                    PackageShareRepository.set_owner(db, name, owner)  # type: ignore
                created.append(name)
                check_in_background(source.id)  # type: ignore

            registry.last_discovered_at = datetime.now()  # type: ignore
            registry.last_error = ("Not registered: " + ", ".join(skipped)) if skipped else None  # type: ignore
            db.commit()
            if created:
                logger.info("Registered images of registry %s: %s", registry.name, ", ".join(created))
            return created
        finally:
            db.close()


class ImageSyncReconciler:
    """Checks the image sources and registries that are due. Called by the SourceReconciler loop."""

    @staticmethod
    def run_once() -> None:
        db = SessionLocal()
        try:
            now = datetime.now()
            registries = [str(r.id) for r in RegistryRepository.list_due_for_discovery(db, now)]
            due = [str(s.id) for s in ImageSourceRepository.list_due(db, now)]
        finally:
            db.close()

        for registry_id in registries:
            try:
                discover(registry_id)
            except SourceBusyError:
                pass
            except Exception as e:
                logger.warning("Discovering images of registry %s failed: %s", registry_id, describe_error(e))

        for source_id in due:
            try:
                check(source_id)
            except SourceBusyError:
                pass
            except Exception:
                logger.exception("Checking image source %s failed", source_id)
