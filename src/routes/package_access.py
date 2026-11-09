from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import src.routes.dtos.user_dto as dtos
from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.repositories.package_repository import PackageRepository
from src.database.repositories.package_share_repository import \
    PackageShareRepository
from src.database.repositories.user_repository import UserRepository
from src.models.package_permissions import Permission
from src.routes import authentication
from src.routes.users import to_lookup_response
from src.services import package_access_service as access

router = APIRouter(prefix="/package-access", tags=["package-access"])


def _ensure_package_exists(db: Session, package_name: str) -> None:
    if not PackageRepository.list_packages(db, package_name):
        raise HTTPException(status_code=404, detail="Package not found")


@router.get("/{package_name}", response_model=dtos.PackageAccessResponse)
async def get_package_access(
    package_name: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    permissions = access.require(db, user, package_name, Permission.VIEW)
    _ensure_package_exists(db, package_name)

    owner_id = PackageShareRepository.get_owner_id(db, package_name)
    owner = UserRepository.get_user_by_id(db, owner_id) if owner_id else None

    shares: list[dtos.PackageShareResponse] = []
    if permissions.manage:
        for share in PackageShareRepository.list_shares(db, package_name):
            share_user = UserRepository.get_user_by_id(db, share.user_id)  # type: ignore
            if share_user is None:
                continue
            shares.append(dtos.PackageShareResponse(
                user=to_lookup_response(share_user),
                can_execute=bool(share.can_execute),
                can_edit=bool(share.can_edit),
            ))
        shares.sort(key=lambda s: s.user.name)

    return dtos.PackageAccessResponse(
        package_name=package_name,
        owner=to_lookup_response(owner) if owner else None,
        permissions=permissions,
        shares=shares,
    )


@router.put("/{package_name}/shares/{user_id}")
async def share_package(
    package_name: str,
    user_id: str,
    request: dtos.ShareRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    access.require(db, user, package_name, Permission.MANAGE)
    _ensure_package_exists(db, package_name)

    if UserRepository.get_user_by_id(db, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")

    if PackageShareRepository.get_owner_id(db, package_name) == user_id:
        raise HTTPException(status_code=400, detail="The owner already has all rights")

    PackageShareRepository.upsert_share(db, package_name, user_id, request.can_execute, request.can_edit)
    return {"message": "Package shared"}


@router.delete("/{package_name}/shares/{user_id}")
async def unshare_package(
    package_name: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    access.require(db, user, package_name, Permission.MANAGE)
    if not PackageShareRepository.delete_share(db, package_name, user_id):
        raise HTTPException(status_code=404, detail="Share not found")
    return {"message": "Share removed"}


@router.put("/{package_name}/owner")
async def set_package_owner(
    package_name: str,
    request: dtos.OwnerRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user),
):
    access.require(db, user, package_name, Permission.MANAGE)
    _ensure_package_exists(db, package_name)

    if request.user_id is None and not user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can remove the owner of a package")

    if request.user_id is not None and UserRepository.get_user_by_id(db, request.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")

    previous_owner_id = PackageShareRepository.get_owner_id(db, package_name)
    PackageShareRepository.set_owner(db, package_name, request.user_id)

    if previous_owner_id and previous_owner_id != request.user_id:
        PackageShareRepository.upsert_share(db, package_name, previous_owner_id, can_execute=True, can_edit=True)

    return {"message": "Owner changed"}
