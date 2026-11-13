"""Container registries: credentials, pull secrets and discovery of images. Managed by admins."""
import logging
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.models.registry_entity import (PullSecretMode,
                                                 RegistryEntity,
                                                 RegistryProvider)
from src.database.repositories.image_source_repository import \
    ImageSourceRepository
from src.database.repositories.registry_repository import RegistryRepository
from src.routes import authentication
from src.routes.dtos.registry_dto import (DiscoveredRepository,
                                          DiscoverResponse,
                                          RegistryCreateRequest,
                                          RegistryResponse, RegistrySettings,
                                          RegistryTestRequest,
                                          RegistryTestResponse,
                                          RegistryUpdateRequest)
from src.routes.sync_errors import call_sync
from src.services import image_sync_service as image_sync
from src.services.registry import image_ref, registry_credentials
from src.services.registry.secret_names import registry_secret_name
from src.services.registry.registry_client import (RegistryClient,
                                                   RegistryCredentials,
                                                   RegistryError)
from src.services.sync.common import SourceBusyError

router = APIRouter(prefix="/registries", tags=["registries"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- helpers

def _get_or_404(db: Session, registry_id: str) -> RegistryEntity:
    registry = RegistryRepository.get(db, registry_id)
    if registry is None:
        raise HTTPException(status_code=404, detail="Registry not found")
    return registry


def _effective_pull_secret(registry: RegistryEntity) -> str | None:
    if registry.pull_secret_mode == PullSecretMode.LOTSE and registry.credential_secret:
        return registry_secret_name(registry.id)  # type: ignore
    if registry.pull_secret_mode == PullSecretMode.EXISTING:
        return registry.pull_secret_name  # type: ignore
    return None


def _to_response(db: Session, registry: RegistryEntity) -> RegistryResponse:
    return RegistryResponse(
        id=registry.id,  # type: ignore
        name=registry.name,  # type: ignore
        host=registry.host,  # type: ignore
        provider=registry.provider,  # type: ignore
        api_url=registry.api_url,  # type: ignore
        username=registry.username,  # type: ignore
        has_token=bool(registry.credential_secret),
        pull_secret_mode=registry.pull_secret_mode,  # type: ignore
        pull_secret_name=registry.pull_secret_name,  # type: ignore
        effective_pull_secret=_effective_pull_secret(registry),
        discovery_path=registry.discovery_path,  # type: ignore
        auto_register=registry.auto_register,  # type: ignore
        default_auto_sync=registry.default_auto_sync,  # type: ignore
        poll_interval_seconds=registry.poll_interval_seconds,  # type: ignore
        last_discovered_at=registry.last_discovered_at,  # type: ignore
        last_error=registry.last_error,  # type: ignore
        image_source_count=len(ImageSourceRepository.list_all(db, registry_id=registry.id)),  # type: ignore
        created_at=registry.created_at,  # type: ignore
    )


def _split_host(host: str, discovery_path: str | None) -> tuple[str, str | None]:
    """"ghcr.io/myorg" -> ("ghcr.io", "myorg") unless a discovery path is given explicitly."""
    host = image_ref.normalize_host(host)
    host, _, path = host.partition("/")
    path = (discovery_path if discovery_path is not None else path) or ""
    path = path.strip().strip("/").lower()
    return host, path or None


def _validated(settings: RegistrySettings) -> tuple[str, str | None]:
    if not settings.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if settings.provider not in RegistryProvider.ALL:
        raise HTTPException(status_code=400, detail=f"Provider must be one of {', '.join(RegistryProvider.ALL)}")
    if settings.pull_secret_mode not in PullSecretMode.ALL:
        raise HTTPException(status_code=400, detail=f"Pull secret mode must be one of {', '.join(PullSecretMode.ALL)}")
    if settings.pull_secret_mode == PullSecretMode.EXISTING and not (settings.pull_secret_name or "").strip():
        raise HTTPException(status_code=400, detail="Enter the name of the existing pull secret")
    if settings.api_url and not settings.api_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=400, detail="API URL must start with https://")
    host, path = _split_host(settings.host, settings.discovery_path)
    if not host or any(c.isspace() for c in host) or "@" in host:
        raise HTTPException(status_code=400, detail="Enter the registry host, e.g. myacr.azurecr.io")
    return host, path


def _test(host: str, provider: str, api_url: str | None, credentials: RegistryCredentials,
          discovery_path: str | None) -> list[str]:
    client = RegistryClient(host, credentials, provider, api_url)
    if discovery_path is not None:
        return client.list_repositories(discovery_path)
    client.check_access()
    return []


def _apply(registry: RegistryEntity, settings: RegistrySettings, host: str, path: str | None) -> None:
    registry.name = settings.name.strip()  # type: ignore
    registry.host = host  # type: ignore
    registry.provider = settings.provider  # type: ignore
    registry.api_url = (settings.api_url or "").rstrip("/") or None  # type: ignore
    registry.username = (settings.username or "").strip() or None  # type: ignore
    registry.pull_secret_mode = settings.pull_secret_mode  # type: ignore
    registry.pull_secret_name = (settings.pull_secret_name or "").strip() or None  # type: ignore
    registry.discovery_path = path  # type: ignore
    registry.auto_register = settings.auto_register and path is not None  # type: ignore
    registry.default_auto_sync = settings.default_auto_sync  # type: ignore
    registry.poll_interval_seconds = settings.poll_interval_seconds  # type: ignore


def _store_credentials(registry_id: str, host: str, username: str | None, token: str) -> str:
    try:
        return registry_credentials.store(registry_id, host, username or "lotse", token)
    except Exception as e:
        logger.exception("Storing registry credentials failed")
        raise HTTPException(status_code=500, detail=f"Could not store the credentials as Kubernetes secret: {e}")


def _discover_in_background(registry_id: str) -> None:
    def run() -> None:
        try:
            image_sync.discover(registry_id)
        except SourceBusyError:
            pass
        except Exception as e:
            logger.warning("Discovering images of registry %s failed: %s", registry_id, e)

    threading.Thread(target=run, daemon=True, name=f"discover-{registry_id[:8]}").start()


# ---------------------------------------------------------------- endpoints

@router.get("/", response_model=list[RegistryResponse])
async def list_registries(
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_user),
):
    """All users: picking a registry for an image source. Contains no credentials."""
    return [_to_response(db, r) for r in RegistryRepository.list_all(db)]


@router.post("/test", response_model=RegistryTestResponse)
async def test_registry(
    request: RegistryTestRequest,
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_admin),
):
    host, path = _split_host(request.host, request.discovery_path)
    credentials = RegistryCredentials(request.username, request.token or None)
    if not request.token and request.registry_id:
        registry = _get_or_404(db, request.registry_id)
        if registry.credential_secret:
            if image_ref.normalize_host(registry.host) != host:  # type: ignore
                return RegistryTestResponse(success=False,
                                            message="Enter the token again to use it with a different host")
            credentials = await run_in_threadpool(registry_credentials.read, registry.credential_secret, host)
            credentials = RegistryCredentials(request.username or credentials.username,  # type: ignore
                                              credentials.password if credentials else None)
    try:
        repositories = await run_in_threadpool(_test, host, request.provider, request.api_url, credentials, path)
    except RegistryError as e:
        return RegistryTestResponse(success=False, message=str(e))
    if path is None:
        return RegistryTestResponse(success=True, message=f"Logged in to {host}")
    return RegistryTestResponse(success=True, repositories=repositories[:50],
                                message=f"Logged in. {len(repositories)} image(s) below '{path}'")


@router.post("/", response_model=RegistryResponse, status_code=201)
async def create_registry(
    request: RegistryCreateRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_admin),
):
    host, path = _validated(request)
    if RegistryRepository.get_by_name(db, request.name.strip()):
        raise HTTPException(status_code=409, detail=f"A registry named {request.name} already exists")
    token = (request.token or "").strip() or None
    if request.pull_secret_mode == PullSecretMode.LOTSE and not token:
        raise HTTPException(status_code=400, detail="A pull secret created by Lotse needs username and token")

    await call_sync(_test, host, request.provider, request.api_url,
                    RegistryCredentials(request.username, token), path)

    registry = RegistryEntity(id=str(uuid.uuid4()), created_by=user.id, created_at=datetime.now())
    _apply(registry, request, host, path)
    if token:
        registry.credential_secret = _store_credentials(registry.id, host, request.username, token)  # type: ignore
    try:
        RegistryRepository.create(db, registry)
    except Exception:
        registry_credentials.delete(registry.credential_secret)  # type: ignore
        raise

    if registry.auto_register:
        _discover_in_background(registry.id)  # type: ignore
    return _to_response(db, registry)


@router.put("/{registry_id}", response_model=RegistryResponse)
async def update_registry(
    registry_id: str,
    request: RegistryUpdateRequest,
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_admin),
):
    registry = _get_or_404(db, registry_id)
    host, path = _validated(request)
    other = RegistryRepository.get_by_name(db, request.name.strip())
    if other is not None and other.id != registry.id:
        raise HTTPException(status_code=409, detail=f"A registry named {request.name} already exists")

    new_token = (request.token or "").strip() or None
    if new_token:
        token = new_token
    elif request.clear_token:
        token = None
    else:
        if registry.credential_secret and image_ref.normalize_host(registry.host) != host:  # type: ignore
            raise HTTPException(status_code=400, detail="Enter the token again when changing the host")
        stored = await call_sync(registry_credentials.read, registry.credential_secret, host)
        token = stored.password if stored else None
    if request.pull_secret_mode == PullSecretMode.LOTSE and not token:
        raise HTTPException(status_code=400, detail="A pull secret created by Lotse needs username and token")

    await call_sync(_test, host, request.provider, request.api_url, RegistryCredentials(request.username, token), path)

    _apply(registry, request, host, path)
    if token:
        # also rewrites the secret when username or host changed
        registry.credential_secret = _store_credentials(registry.id, host, request.username, token)  # type: ignore
    elif registry.credential_secret:
        registry_credentials.delete(registry.credential_secret)  # type: ignore
        registry.credential_secret = None  # type: ignore
    registry.last_error = None  # type: ignore
    db.commit()

    if registry.auto_register:
        _discover_in_background(registry.id)  # type: ignore
    return _to_response(db, registry)


@router.delete("/{registry_id}")
async def delete_registry(
    registry_id: str,
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_admin),
):
    registry = _get_or_404(db, registry_id)
    sources = ImageSourceRepository.list_all(db, registry_id=registry_id)
    if sources:
        names = ", ".join(str(s.package_name) for s in sources[:10])
        raise HTTPException(status_code=409, detail=f"Disconnect the image sources first: {names}")
    registry_credentials.delete(registry.credential_secret)  # type: ignore
    RegistryRepository.delete(db, registry)
    return {"message": "Registry deleted"}


@router.get("/{registry_id}/repositories", response_model=list[DiscoveredRepository])
async def list_repositories(
    registry_id: str,
    path: str | None = None,
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_user),
):
    """Images below the discovery path (or `path`), for picking one when connecting a package."""
    registry = _get_or_404(db, registry_id)
    client = await call_sync(image_sync.client_for, registry)
    repositories = await call_sync(client.list_repositories, path if path is not None else registry.discovery_path)
    registered = {str(s.repository): str(s.package_name)
                  for s in ImageSourceRepository.list_all(db, registry_id=registry_id)}
    result = []
    for repository in repositories:
        name = image_sync.package_name_for(repository)
        registered_as = registered.get(repository)
        result.append(DiscoveredRepository(
            repository=repository,
            image=image_sync.image_name(registry, repository),
            package_name=name,
            registered_as=registered_as,
            name_taken=registered_as is None and image_sync.name_taken(db, name),
        ))
    return result


@router.post("/{registry_id}/discover", response_model=DiscoverResponse)
async def discover_now(
    registry_id: str,
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_admin),
):
    registry = _get_or_404(db, registry_id)
    if registry.discovery_path is None:
        raise HTTPException(status_code=400, detail="The registry has no discovery path")
    created = await call_sync(image_sync.discover, registry_id)
    db.expire_all()
    return DiscoverResponse(created=created, registry=_to_response(db, _get_or_404(db, registry_id)))
