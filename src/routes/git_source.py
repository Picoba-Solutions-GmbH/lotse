"""Git sources: Lotse watches a repository and deploys new tags as package versions."""
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime
from typing import Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.models.git_source_entity import GitSourceEntity
from src.database.repositories.git_source_repository import \
    GitSourceRepository
from src.database.repositories.package_repository import PackageRepository
from src.models.package_permissions import Permission
from src.routes import authentication
from src.routes.dtos.git_source_dto import (GitConnectionTestRequest,
                                            GitConnectionTestResponse,
                                            GitSourceCreateRequest,
                                            GitSourceResponse,
                                            GitSourceSettings,
                                            GitSourceUpdateRequest,
                                            GitSyncRequest, GitSyncResponse,
                                            GitTagResponse)
from src.services import git_sync_service as git_sync
from src.services import package_access_service as access
from src.services.git import git_client, git_credentials
from src.services.git.git_client import GitAuth, GitError, TagVersion
from src.services.git.git_package_config import SyncConfigError

router = APIRouter(prefix="/git-sources", tags=["git-sources"])
logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------- helpers

def _get_or_404(db: Session, source_id: str) -> GitSourceEntity:
    source = GitSourceRepository.get(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Git source not found")
    return source


def _to_response(db: Session, user: CurrentUser, source: GitSourceEntity) -> GitSourceResponse:
    active = PackageRepository.get_package(db, source.package_name)  # type: ignore
    active_version = str(active.version) if active else None
    can_edit = access.get_permissions(db, user, source.package_name).edit  # type: ignore
    return GitSourceResponse(
        id=source.id,  # type: ignore
        package_name=source.package_name,  # type: ignore
        repo_url=source.repo_url,  # type: ignore
        path=source.path,  # type: ignore
        tag_prefix=source.tag_prefix,  # type: ignore
        username=source.username,  # type: ignore
        has_token=bool(source.credential_secret),
        auto_sync=source.auto_sync,  # type: ignore
        prune_previous=source.prune_previous,  # type: ignore
        poll_interval_seconds=source.poll_interval_seconds,  # type: ignore
        status=git_sync.compute_status(source, active_version),
        active_version=active_version,
        latest_tag=source.latest_tag,  # type: ignore
        latest_version=git_client.version_of(source.latest_tag, source.tag_prefix),  # type: ignore
        latest_commit=source.latest_commit,  # type: ignore
        last_synced_tag=source.last_synced_tag,  # type: ignore
        last_synced_commit=source.last_synced_commit,  # type: ignore
        last_synced_at=source.last_synced_at,  # type: ignore
        last_checked_at=source.last_checked_at,  # type: ignore
        last_error=source.last_error,  # type: ignore
        webhook_path=f"/git-sources/{source.id}/webhook",
        webhook_token=source.webhook_token if can_edit else None,  # type: ignore
        can_edit=can_edit,
        created_at=source.created_at,  # type: ignore
    )


def _validated_settings(settings: GitSourceSettings) -> tuple[str, str, str]:
    try:
        url = git_client.validate_repo_url(settings.repo_url)
        path = git_client.normalize_path(settings.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return url, path, (settings.tag_prefix or "").strip()


async def _call_git(function: Callable[..., T], *args) -> T:
    """Runs blocking git and sync calls in a worker thread and maps their errors to HTTP errors."""
    try:
        return await run_in_threadpool(function, *args)
    except HTTPException:
        raise
    except git_sync.SourceBusyError:
        raise HTTPException(status_code=409, detail="A check or sync of this source is already running")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SyncConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GitError as e:
        raise HTTPException(status_code=502, detail=f"Git: {e}")
    except Exception as e:
        logger.exception("Git operation failed")
        raise HTTPException(status_code=500, detail=git_sync.describe_error(e))


async def _list_versions(url: str, auth: GitAuth, prefix: str) -> list[TagVersion]:
    tags = await _call_git(git_client.list_tags, url, auth)
    return git_client.parse_versions(tags, prefix)


def _apply_versions(db: Session, source: GitSourceEntity, versions: list[TagVersion]) -> None:
    """Remembers the latest tag. Versions that already exist in Lotse count as synced, so auto sync
    only deploys tags that are newer than them."""
    deployed = {str(p.version) for p in PackageRepository.list_packages(db, source.package_name)}  # type: ignore
    baseline = git_sync.baseline_tag(versions, deployed)
    latest = versions[0] if versions else None
    source.last_synced_tag = baseline.tag if baseline else None  # type: ignore
    source.last_synced_commit = None  # type: ignore
    source.latest_tag = latest.tag if latest else None  # type: ignore
    source.latest_commit = latest.commit if latest else None  # type: ignore
    source.last_checked_at = datetime.now()  # type: ignore
    source.last_error = None  # type: ignore
    source.last_failed_commit = None  # type: ignore


def _store_token(source_id: str, token: str) -> str:
    try:
        return git_credentials.store_token(source_id, token)
    except Exception as e:
        logger.exception("Storing the Git access token failed")
        raise HTTPException(status_code=500,
                            detail=f"Could not store the access token as Kubernetes secret: {e}")


# ---------------------------------------------------------------- endpoints

@router.get("/", response_model=list[GitSourceResponse])
async def list_git_sources(
    package_name: str | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    sources = GitSourceRepository.list_all(db, access.visible_package_names(db, user))
    if package_name:
        sources = [s for s in sources if s.package_name == package_name]
    return [_to_response(db, user, s) for s in sources]


@router.post("/test", response_model=GitConnectionTestResponse)
async def test_connection(
    request: GitConnectionTestRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    try:
        url = git_client.validate_repo_url(request.repo_url)
    except ValueError as e:
        return GitConnectionTestResponse(success=False, message=str(e))

    token = request.token
    if not token and request.source_id:
        source = _get_or_404(db, request.source_id)
        access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
        if source.credential_secret and not git_client.same_origin(url, source.repo_url):  # type: ignore
            return GitConnectionTestResponse(
                success=False, message="Enter the token again to use it with a different server")
        token = await run_in_threadpool(git_credentials.read_token, source.credential_secret)  # type: ignore

    try:
        versions = await _list_versions(url, GitAuth(request.username, token), (request.tag_prefix or "").strip())
    except HTTPException as e:
        return GitConnectionTestResponse(success=False, message=str(e.detail))

    if not versions:
        message = f"Connected, but no tags match '{request.tag_prefix}<version>' yet"
    else:
        message = f"Connected. {len(versions)} version tag(s), newest: {versions[0].tag}"
    return GitConnectionTestResponse(
        success=True, message=message,
        tags=[GitTagResponse(tag=v.tag, version=v.version, commit=v.commit) for v in versions[:10]])


@router.post("/", response_model=GitSourceResponse, status_code=201)
async def create_git_source(
    request: GitSourceCreateRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    package_name = request.package_name.strip()
    if not package_name:
        raise HTTPException(status_code=400, detail="Package name is required")
    if GitSourceRepository.get_by_package(db, package_name):
        raise HTTPException(status_code=409, detail=f"Package {package_name} is already connected to a repository")

    url, path, prefix = _validated_settings(request)
    token = (request.token or "").strip() or None
    versions = await _list_versions(url, GitAuth(request.username, token), prefix)

    # after the connection test, so that a failed test doesn't claim the package name
    access.claim_or_check_deploy(db, user, package_name)

    source = GitSourceEntity(
        id=str(uuid.uuid4()),
        package_name=package_name,
        repo_url=url,
        path=path,
        tag_prefix=prefix,
        username=(request.username or "").strip() or None,
        auto_sync=request.auto_sync,
        prune_previous=request.prune_previous,
        poll_interval_seconds=request.poll_interval_seconds,
        webhook_token=secrets.token_urlsafe(24),
        created_by=user.id,
        created_at=datetime.now(),
    )
    _apply_versions(db, source, versions)
    if token:
        source.credential_secret = _store_token(source.id, token)  # type: ignore

    try:
        GitSourceRepository.create(db, source)
    except Exception:
        git_credentials.delete_token(source.credential_secret)  # type: ignore
        raise

    if source.auto_sync:
        git_sync.check_in_background(source.id)  # type: ignore
    return _to_response(db, user, source)


@router.get("/{source_id}", response_model=GitSourceResponse)
async def get_git_source(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.VIEW)  # type: ignore
    return _to_response(db, user, source)


@router.put("/{source_id}", response_model=GitSourceResponse)
async def update_git_source(
    source_id: str,
    request: GitSourceUpdateRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    url, path, prefix = _validated_settings(request)
    username = (request.username or "").strip() or None
    new_token = (request.token or "").strip() or None

    if new_token:
        token = new_token
    elif request.clear_token:
        token = None
    else:
        if source.credential_secret and not git_client.same_origin(url, source.repo_url):  # type: ignore
            # otherwise anyone who can edit could send the stored token to a server of their choice
            raise HTTPException(status_code=400,
                                detail="Enter the token again (or remove it) when moving to a different server")
        token = await _call_git(git_credentials.read_token, source.credential_secret)
    versions = await _list_versions(url, GitAuth(username, token), prefix)

    if new_token:
        source.credential_secret = _store_token(source.id, new_token)  # type: ignore
    elif request.clear_token and source.credential_secret:
        git_credentials.delete_token(source.credential_secret)  # type: ignore
        source.credential_secret = None  # type: ignore

    repository_changed = (url, path, prefix) != (source.repo_url, source.path, source.tag_prefix)
    source.repo_url = url  # type: ignore
    source.path = path  # type: ignore
    source.tag_prefix = prefix  # type: ignore
    source.username = username  # type: ignore
    source.auto_sync = request.auto_sync  # type: ignore
    source.prune_previous = request.prune_previous  # type: ignore
    source.poll_interval_seconds = request.poll_interval_seconds  # type: ignore
    if repository_changed:
        _apply_versions(db, source, versions)
    db.commit()

    if source.auto_sync:
        git_sync.check_in_background(source.id)  # type: ignore
    return _to_response(db, user, source)


@router.delete("/{source_id}")
async def delete_git_source(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    git_credentials.delete_token(source.credential_secret)  # type: ignore
    GitSourceRepository.delete(db, source)
    return {"message": "Git source deleted. Deployed versions were kept."}


@router.get("/{source_id}/tags", response_model=list[GitTagResponse])
async def list_tags(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.VIEW)  # type: ignore
    versions = await _call_git(git_sync.list_versions, source)
    packages = {str(p.version): p for p in PackageRepository.list_packages(db, source.package_name)}  # type: ignore
    return [
        GitTagResponse(tag=v.tag, version=v.version, commit=v.commit,
                       deployed=v.version in packages,
                       active=bool(packages[v.version].active) if v.version in packages else False)
        for v in versions
    ]


@router.post("/{source_id}/refresh", response_model=GitSourceResponse)
async def refresh_git_source(
    source_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    await _call_git(git_sync.check, source_id)
    db.expire_all()
    return _to_response(db, user, _get_or_404(db, source_id))


@router.post("/{source_id}/sync", response_model=GitSyncResponse)
async def sync_git_source(
    source_id: str,
    request: GitSyncRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    source = _get_or_404(db, source_id)
    access.require(db, user, source.package_name, Permission.EDIT)  # type: ignore
    result = await _call_git(git_sync.sync, source_id, request.tag)
    db.expire_all()
    return GitSyncResponse(action=result.action, tag=result.tag, version=result.version, commit=result.commit,
                           source=_to_response(db, user, _get_or_404(db, source_id)))


@router.post("/{source_id}/webhook", status_code=202)
async def webhook(
    source_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Triggers a check of the source. The payload is ignored, Lotse always asks the repository itself.

    Authentication, one of:
    - header `X-Lotse-Token: <token>` (Azure DevOps service hooks, Gitea, curl)
    - GitHub/Gitea webhook secret = token (`X-Hub-Signature-256`)
    - query parameter `?token=<token>`
    """
    source = GitSourceRepository.get(db, source_id)
    expected = str(source.webhook_token) if source else secrets.token_urlsafe(24)

    token = request.headers.get("x-lotse-token") or request.query_params.get("token")
    signature = request.headers.get("x-hub-signature-256")
    if token:
        valid = hmac.compare_digest(token.encode(), expected.encode())
    elif signature:
        body = await request.body()
        digest = "sha256=" + hmac.new(expected.encode(), body, hashlib.sha256).hexdigest()
        valid = hmac.compare_digest(signature.encode(), digest.encode())
    else:
        valid = False

    if source is None or not valid:
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    git_sync.check_in_background(source_id)
    return JSONResponse(status_code=202, content={"accepted": True})
