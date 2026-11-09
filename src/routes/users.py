from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import src.routes.dtos.user_dto as dtos
from src.authentication.roles_type import RoleType, parse_role
from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.models.user_entity import UserEntity
from src.database.repositories.package_share_repository import \
    PackageShareRepository
from src.database.repositories.user_repository import UserRepository
from src.routes import authentication
from src.utils.hasher import get_password_hash

router = APIRouter(prefix="/users", tags=["users"])


def to_user_response(user: UserEntity) -> dtos.UserResponse:
    return dtos.UserResponse(
        id=user.id,  # type: ignore
        name=user.name,  # type: ignore
        display_name=user.display_name,  # type: ignore
        email=user.email,  # type: ignore
        role=parse_role(user.role),  # type: ignore
        is_ldap=bool(user.is_ldap),
    )


def to_lookup_response(user: UserEntity) -> dtos.UserLookupResponse:
    return dtos.UserLookupResponse(
        id=user.id,  # type: ignore
        name=user.name,  # type: ignore
        display_name=user.display_name,  # type: ignore
    )


@router.get("", response_model=list[dtos.UserResponse])
async def list_users(
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_admin),
):
    return [to_user_response(user) for user in UserRepository.list_users(db)]


@router.get("/lookup", response_model=list[dtos.UserLookupResponse])
async def lookup_users(
    q: str = Query("", description="Part of the user name, display name or email"),
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_user),
):
    return [to_lookup_response(user) for user in UserRepository.search_users(db, q.strip())]


@router.post("", response_model=dtos.UserResponse, status_code=201)
async def create_user(
    request: dtos.CreateUserRequest,
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_admin),
):
    if UserRepository.get_user_by_name(db, request.name.strip()):
        raise HTTPException(status_code=409, detail=f"User {request.name} already exists")

    user = UserRepository.create_user(
        db,
        name=request.name.strip(),
        hashed_password=get_password_hash(request.password),
        role=request.role,
        display_name=request.display_name,
        email=request.email,
    )
    return to_user_response(user)


@router.put("/{user_id}", response_model=dtos.UserResponse)
async def update_user(
    user_id: str,
    request: dtos.UpdateUserRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(authentication.require_admin),
):
    user = UserRepository.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_demotion = (request.role is not None and request.role != RoleType.ADMIN
                   and parse_role(user.role) == RoleType.ADMIN)  # type: ignore
    if is_demotion:
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
        if UserRepository.count_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="The last admin cannot be demoted")

    hashed_password = None
    if request.password:
        if user.is_ldap:
            raise HTTPException(status_code=400, detail="Passwords of active directory users are managed in the AD")
        hashed_password = get_password_hash(request.password)

    updated = UserRepository.update_user(db, user_id, hashed_password=hashed_password, role=request.role)
    return to_user_response(updated)  # type: ignore


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(authentication.require_admin),
):
    user = UserRepository.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")

    if parse_role(user.role) == RoleType.ADMIN and UserRepository.count_admins(db) <= 1:  # type: ignore
        raise HTTPException(status_code=400, detail="The last admin cannot be deleted")

    # Packages owned by the user become unowned (admin only) until an admin assigns a new owner.
    PackageShareRepository.remove_user_access(db, user_id)
    UserRepository.delete_user(db, user_id)
    return {"message": "User deleted"}
