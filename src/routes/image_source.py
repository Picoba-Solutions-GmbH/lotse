"""Image sources: Lotse watches an image in a registry and deploys new semver tags as package versions."""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.models.image_source_entity import ImageSourceEntity
from src.database.repositories.image_source_repository import \
    ImageSourceRepository
from src.database.repositories.package_repository import PackageRepository
from src.database.repositories.registry_repository import RegistryRepository
from src.models.package_permissions import Permission
from src.routes import authentication
from src.routes.dtos.git_source_dto import GitTagResponse
from src.routes.dtos.image_source_dto import (ImageSourceCreateRequest,
                                              ImageSourceResponse,
                                              ImageSourceSettings,
                                              ImageSourceUpdateRequest,
                                              ImageSyncRequest,
                                              ImageSyncResponse)
from src.routes.sync_errors import call_sync
from src.routes.webhook_auth import require_webhook_token
from src.services import image_sync_service as image_sync
from src.services import package_access_service as access
from src.services.registry import image_ref
from src.services.sync.versions import (TagVersion, baseline_tag,
                                        parse_versions, version_of)

router = APIRouter(prefix="/image-sources", tags=["image-sources"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- helpers

def _get_or_404(db: Session, source_id: str) -> ImageSourceEntity:
    source = ImageSourceRepository.get(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Image source not found")
    return source


def _to_response(db: Session, user: CurrentUser, source: ImageSourceEntity) -> ImageSourceResponse:
    active = PackageRepository.get_package(db, source.package_name)  # type: ignore
    active_version = str(active.version) if active else None
    can_edit = access.get_permissions(db, user, source.package_name).edit  # type: ignore
    registry = RegistryRepository.get(db, source.registry_id)  # type: ignore
    return ImageSourceResponse(
        id=source.id,  # type: ignore
        package_name=source.package_name,  # type: ignore
        registry_id=source.registry_id,  # type: ignore
        registry_name=registry.name if registry else None,  # type: ignore
        repository=source.repository,  # type: ignore
        image=(image_sync.image_name(registry, source.repository)  # type: ignore
               if registry else str(source.repository)),
        tag_prefix=source.tag_prefix,  # type: ignore
        auto_sync=source.auto_sync,  # type: ignore
        prune_previous=source.prune_previous,  # type: ignore
        poll_interval_seconds=source.poll_interval_seconds,  # type: ignore
        status=image_sync.compute_status(source, active_version),
        active_version=active_version,
        latest_tag=source.latest_tag,  # type: ignore
        latest_version=version_of(source.latest_tag, source.tag_prefix),  # type: ignore
        latest_digest=source.latest_digest,  # type: ignore
        last_synced_tag=source.last_synced_tag,  # type: ignore
        last_synced_digest=source.last_synced_digest,  # type: ignore
        last_synced_at=source.last_synced_at,  # type: ignore
        last_checked_at=source.last_checked_at,  # type: ignore
        last_error=source.last_error,  # type: ignore
        webhook_path=f"/image-sources/{source.id}/webhook",
        webhook_token=source.webhook_token if can_edit else None,  # type: ignore
        can_edit=can_edit,
        created_at=source.created_at,  # type: ignore
    )


def _list_tags(db: Session, registry_id: str, repository: str, prefix: str) -> list[TagVersion]:
    registry = RegistryRepository.get(db, registry_id)
    if registry is None:
        raise LookupError("Registry not found")
    tags = image_sync.client_for(registry).list_tags(repository)
    return parse_versions({tag: "" for tag in tags}, prefix)


def _validated(settings: ImageSourceSettings) -> tuple[str, str]:
    repository = settings.repository.strip().strip("/").lower()
    if not repository or any(c.isspace() for c in repository) or ".." in repository.split("/"):
        raise HTTPException(status_code=400, detail="Enter the image path inside the registry, e.g. lotse/my-app")
    return repository, (settings.tag_prefix or "").strip()


def _apply_versions(db: Session, source: ImageSourceEntity, versions: list[TagVersion]) -> None:
    """Versions that already exist count as synced: auto sync starts with the tags after them."""
    deployed = {str(p.version) for p in PackageRepository.list_packages(db, source.package_name)}  # type: ignore
    baseline = baseline_tag(versions, deployed)
    source.last_synced_tag = baseline.tag if baseline else None  # type: ignore
    source.last_synced_digest = None  # type: ignore
    source.latest_tag = versions[0].tag if versions else None  # type: ignore
    source.latest_digest = None  # type: ignore
    source.last_error = None  # type: ignore
    source.last_failed_digest = None  # type: ignore


# ---------------------------------------------------------------- endpoints

@router.get("/", response_model=list[ImageSourceResponse])
async def list_image_sources(
    package_name: str | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    sources = ImageSourceRepository.list_all(db, access.visible_package_names(db, user))
    if package_name:
        sources = [s for s in sources if s.package_name == package_name]
    return [_to_response(db, user, s) for s in sources]


@router.post("/", response_model=ImageSourceResponse, status_code=201)
async def create_image_source(
    request: ImageSourceCreateRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    repository, prefix = _validated(request)
    registry = RegistryRepository.get(db, request.registry_id)
    if registry is None:
        raise HTTPException(status_code=404, detail="Registry not found")
    repository = image_ref.normalize_repository(registry.host, repository)  # type: ignore
    package_name = (request.package_name or "").strip() or image_sync.package_name_for(repository)
    if image_sync.name_taken(db, package_name):
        raise HTTPException(status_code=409, detail=f"Package {package_name} is already connected to a source")

    versions = await call_sync(_list_tags, db, request.registry_id, repository, prefix)
    access.claim_or_check_deploy(db, user, package_name)

    source = image_sync.create_source(db, registry, repository, package_name, user.id, request.auto_sync,
                                      prefix, request.prune_previous, request.poll_interval_seconds)
    _apply_versions(db, source, versions)
    source.last_checked_at = datetime.now()  # type: ignore
    db.commit()
    if source.auto_sync:
        image_sync.check_in_background(source.id)  # type: ignore
    return _to_response(db, user, source)


@router.get("/{source_id}", response_model=ImageSourceResponse)
async def get_image_source(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.VIEW)  # type: ignore
    return _to_response(db, user, source)


@router.put("/{source_id}", response_model=ImageSourceResponse)
async def update_image_source(
    source_id: str,
    request: ImageSourceUpdateRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    repository, prefix = _validated(request)
    registry = RegistryRepository.get(db, request.registry_id)
    if registry is None:
        raise HTTPException(status_code=404, detail="Registry not found")
    repository = image_ref.normalize_repository(registry.host, repository)  # type: ignore
    versions = await call_sync(_list_tags, db, request.registry_id, repository, prefix)

    image_changed = (request.registry_id, repository, prefix) != (source.registry_id, source.repository,
                                                                  source.tag_prefix)
    source.registry_id = request.registry_id  # type: ignore
    source.repository = repository  # type: ignore
    source.tag_prefix = prefix  # type: ignore
    source.auto_sync = request.auto_sync  # type: ignore
    source.prune_previous = request.prune_previous  # type: ignore
    source.poll_interval_seconds = request.poll_interval_seconds  # type: ignore
    if image_changed:
        _apply_versions(db, source, versions)
    db.commit()

    if source.auto_sync:
        image_sync.check_in_background(source.id)  # type: ignore
    return _to_response(db, user, source)


@router.delete("/{source_id}")
async def delete_image_source(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    ImageSourceRepository.delete(db, source)
    return {"message": "Image source deleted. Deployed versions were kept."}


@router.get("/{source_id}/tags", response_model=list[GitTagResponse])
async def list_tags(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.VIEW)  # type: ignore
    versions = await call_sync(image_sync.list_versions, db, source)
    packages = {str(p.version): p for p in PackageRepository.list_packages(db, source.package_name)}  # type: ignore
    return [
        GitTagResponse(tag=v.tag, version=v.version,
                       commit=str(packages[v.version].source_commit or "") if v.version in packages else "",
                       deployed=v.version in packages,
                       active=bool(packages[v.version].active) if v.version in packages else False)
        for v in versions
    ]


@router.post("/{source_id}/refresh", response_model=ImageSourceResponse)
async def refresh_image_source(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    await call_sync(image_sync.check, source_id)
    db.expire_all()
    return _to_response(db, user, _get_or_404(db, source_id))


@router.post("/{source_id}/sync", response_model=ImageSyncResponse)
async def sync_image_source(
    source_id: str,
    request: ImageSyncRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    result = await call_sync(image_sync.sync, source_id, request.tag)
    db.expire_all()
    return ImageSyncResponse(action=result.action, tag=result.tag, version=result.version, digest=result.digest,
                             source=_to_response(db, user, _get_or_404(db, source_id)))


@router.post("/{source_id}/webhook", status_code=202)
async def webhook(
    source_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Triggers a check of the image. The payload is ignored, Lotse always asks the registry itself.
    Authentication: see `require_webhook_token`."""
    source = ImageSourceRepository.get(db, source_id)
    await require_webhook_token(request, str(source.webhook_token) if source else None)
    image_sync.check_in_background(source_id)
    return JSONResponse(status_code=202, content={"accepted": True})
