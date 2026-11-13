"""Deploys package versions from Git tags, similar to ArgoCD.

- check(): looks for new tags of a source and, with auto sync, deploys the newest one
- sync():  deploys the newest or a given tag
- a background thread calls check() for every source whose poll interval has elapsed

Every operation on a source holds a Postgres advisory lock, so the poller, webhooks and users never
deploy the same source at the same time, even with several Lotse replicas.
"""
import logging
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import SYSTEM_ADMIN
from src.database.database_access import SessionLocal
from src.database.models.git_source_entity import GitSourceEntity
from src.database.repositories.git_source_repository import \
    GitSourceRepository
from src.database.repositories.package_repository import PackageRepository
from src.services import image_sync_service as image_sync
from src.services import package_deploy_service as deployment
from src.services.git import git_client, git_credentials
from src.services.git.git_client import GitAuth, TagVersion
from src.services.git.git_package_config import (CONFIG_FILE_NAMES,
                                                 prepare_config)
from src.services.sync import common
from src.services.sync.common import (SourceBusyError,  # noqa: F401  (re-exported)
                                      SyncConfigError, SyncStatus,
                                      describe_error)
from src.services.sync.versions import baseline_tag  # noqa: F401  (re-exported)
from src.utils import config

logger = logging.getLogger(__name__)

_IGNORED_NAMES = {".git", "__pycache__"}

_source_lock = common.source_lock
_is_permanent = common.is_permanent
_remove_tree = common.remove_tree


@dataclass
class SyncResult:
    # "deployed": a new version was created, "activated": an existing version became the default
    action: str
    tag: str
    version: str
    commit: str


# ---------------------------------------------------------------- helpers

def _ignore_for_copy(directory: str, names: list[str]) -> list[str]:
    # symlinks are skipped: they could point to files of the Lotse host that would end up in the pod
    return [name for name in names
            if name in _IGNORED_NAMES or os.path.islink(os.path.join(directory, name))]


def auth_for(source: GitSourceEntity) -> GitAuth:
    return GitAuth(username=source.username, token=git_credentials.read_token(source.credential_secret))  # type: ignore


def list_versions(source: GitSourceEntity) -> list[TagVersion]:
    tags = git_client.list_tags(source.repo_url, auth_for(source))  # type: ignore
    return git_client.parse_versions(tags, source.tag_prefix)  # type: ignore


def compute_status(source: GitSourceEntity, active_version: str | None) -> str:
    return common.compute_status(source.last_checked_at, source.last_error, source.latest_tag,  # type: ignore
                                 source.tag_prefix, active_version)  # type: ignore


# ---------------------------------------------------------------- check / sync

def check(source_id: str) -> None:
    """Refreshes the latest tag of a source and deploys it if auto sync is on. Errors end up in last_error."""
    with _source_lock(source_id) as acquired:
        if not acquired:
            raise SourceBusyError()
        db = SessionLocal()
        try:
            source = GitSourceRepository.get(db, source_id)
            if source is not None:
                _check_locked(db, source)
        finally:
            db.close()


def sync(source_id: str, tag: str | None = None) -> SyncResult:
    """Deploys `tag`, or the newest tag. Raises on errors; they are stored in last_error as well."""
    with _source_lock(source_id) as acquired:
        if not acquired:
            raise SourceBusyError()
        db = SessionLocal()
        try:
            source = GitSourceRepository.get(db, source_id)
            if source is None:
                raise LookupError("Git source not found")
            try:
                versions = list_versions(source)
            except Exception as e:
                _record_failure(db, source, e, commit=None)
                raise
            _record_latest(source, versions)
            db.commit()

            if tag is None:
                if not versions:
                    raise LookupError(f"The repository has no tags matching '{source.tag_prefix}<version>'")
                target = versions[0]
            else:
                target = next((v for v in versions if v.tag == tag), None)
                if target is None:
                    raise LookupError(f"Tag '{tag}' doesn't exist or doesn't match '{source.tag_prefix}<version>'")
            return _sync_locked(db, source, target)
        finally:
            db.close()


def _record_latest(source: GitSourceEntity, versions: list[TagVersion]) -> None:
    latest = versions[0] if versions else None
    source.latest_tag = latest.tag if latest else None  # type: ignore
    source.latest_commit = latest.commit if latest else None  # type: ignore
    source.last_checked_at = datetime.now()  # type: ignore
    # an earlier failed deployment of the same commit is still a problem
    if latest is None or latest.commit != source.last_failed_commit:
        source.last_error = None  # type: ignore


def _record_failure(db: Session, source: GitSourceEntity, error: Exception, commit: str | None) -> None:
    db.rollback()
    source.last_checked_at = datetime.now()  # type: ignore
    source.last_error = describe_error(error)  # type: ignore
    if commit and _is_permanent(error):
        source.last_failed_commit = commit  # type: ignore
    db.commit()


def _check_locked(db: Session, source: GitSourceEntity) -> None:
    try:
        versions = list_versions(source)
    except Exception as e:
        logger.warning("Checking Git source of %s failed: %s", source.package_name, e)
        _record_failure(db, source, e, commit=None)
        return

    _record_latest(source, versions)
    db.commit()

    if not source.auto_sync or not versions:
        return
    latest = versions[0]
    if latest.commit == source.last_failed_commit:
        return
    last_synced_version = git_client.version_of(source.last_synced_tag, source.tag_prefix)  # type: ignore
    if not git_client.is_newer(latest.version, last_synced_version):
        return

    try:
        result = _sync_locked(db, source, latest)
        logger.info("Git sync deployed %s %s (%s)", source.package_name, result.version, result.commit[:7])
    except Exception as e:
        logger.warning("Git sync of %s %s failed: %s", source.package_name, latest.tag, describe_error(e))


def _sync_locked(db: Session, source: GitSourceEntity, target: TagVersion) -> SyncResult:
    try:
        result = _deploy_tag(db, source, target)
    except Exception as e:
        _record_failure(db, source, e, commit=target.commit)
        raise

    # the newest tag ever synced: deploying an older tag (roll back) must not make auto sync
    # deploy the newer ones again
    newest_synced = git_client.version_of(source.last_synced_tag, source.tag_prefix)  # type: ignore
    if git_client.is_newer(target.version, newest_synced):
        source.last_synced_tag = target.tag  # type: ignore
        source.last_synced_commit = result.commit  # type: ignore
    source.last_synced_at = datetime.now()  # type: ignore
    source.last_error = None  # type: ignore
    source.last_failed_commit = None  # type: ignore
    db.commit()
    return result


def _deploy_tag(db: Session, source: GitSourceEntity, target: TagVersion) -> SyncResult:
    package_name: str = source.package_name  # type: ignore
    existing = PackageRepository.get_package(db, package_name, target.version)
    if existing is not None:
        if existing.source_id == source.id and existing.source_commit == target.commit:
            PackageRepository.set_active_package(db, package_name, target.version)
            return SyncResult(action="activated", tag=target.tag, version=target.version, commit=target.commit)
        origin = (f"from commit {str(existing.source_commit)[:7]}" if existing.source_commit
                  else "by an upload")
        raise SyncConfigError(
            f"Version {target.version} already exists (deployed {origin}). "
            f"Push a new tag, or delete version {target.version} in Lotse to deploy it from Git.")

    # short name: git's own paths below it are long, which matters on Windows
    work_dir = Path(config.GIT_WORK_ROOT) / uuid.uuid4().hex[:12]
    try:
        commit = git_client.checkout(source.repo_url, auth_for(source), target.tag,  # type: ignore
                                     work_dir, source.path)  # type: ignore
        package_root = work_dir / source.path if source.path else work_dir  # type: ignore
        config_path = next((package_root / name for name in CONFIG_FILE_NAMES
                            if (package_root / name).is_file()), None)
        if config_path is None:
            raise SyncConfigError(f"No config.yaml in '{source.path or '/'}' at tag {target.tag}")

        previous = PackageRepository.get_package(db, package_name)
        config_text = prepare_config(config_path.read_text(encoding="utf-8"), package_name, target.version,
                                     previous.config if previous else None)  # type: ignore
        # runtime: container -> the image must exist, the version is pinned to its digest
        config_text = image_sync.pin_image_digest(db, config_text)

        def copy_checkout(package_dir: Path, _) -> None:
            shutil.copytree(package_root, package_dir, dirs_exist_ok=True, ignore=_ignore_for_copy)

        deployment.deploy_package(
            db, SYSTEM_ADMIN, config_text, copy_checkout,
            set_active=True, delete_previous_versions=bool(source.prune_previous),
            source=deployment.DeploymentSource(type="git", source_id=source.id,  # type: ignore
                                               ref=target.tag, commit=commit),
        )
        return SyncResult(action="deployed", tag=target.tag, version=target.version, commit=commit)
    finally:
        _remove_tree(work_dir)


def check_in_background(source_id: str) -> None:
    def run() -> None:
        try:
            check(source_id)
        except SourceBusyError:
            pass
        except Exception:
            logger.exception("Checking Git source %s failed", source_id)

    threading.Thread(target=run, daemon=True, name=f"git-check-{source_id[:8]}").start()


# ---------------------------------------------------------------- reconciler

class GitSyncReconciler:
    """Checks the Git sources that are due. Called by the SourceReconciler loop."""

    @staticmethod
    def run_once() -> None:
        db = SessionLocal()
        try:
            due = [str(source.id) for source in GitSourceRepository.list_due(db, datetime.now())]
        finally:
            db.close()

        for source_id in due:
            try:
                check(source_id)
            except SourceBusyError:
                pass
            except Exception:
                logger.exception("Checking Git source %s failed", source_id)
