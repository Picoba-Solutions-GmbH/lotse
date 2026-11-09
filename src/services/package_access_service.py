from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.models.task_entity import TaskEntity
from src.database.repositories.package_repository import PackageRepository
from src.database.repositories.package_share_repository import \
    PackageShareRepository
from src.database.repositories.task_repository import TaskRepository
from src.models.package_permissions import PackagePermissions, Permission


ALL_PERMISSIONS = PackagePermissions(view=True, execute=True, edit=True, manage=True)
NO_PERMISSIONS = PackagePermissions()


def get_permissions(db: Session, user: CurrentUser, package_name: str) -> PackagePermissions:
    if user.is_admin:
        return ALL_PERMISSIONS

    owner_id = PackageShareRepository.get_owner_id(db, package_name)
    if owner_id is not None and owner_id == user.id:
        return ALL_PERMISSIONS

    share = PackageShareRepository.get_share(db, package_name, user.id)
    if share is None:
        return NO_PERMISSIONS

    return PackagePermissions(
        view=True,
        execute=bool(share.can_execute),
        edit=bool(share.can_edit),
        manage=False,
    )


def require(db: Session, user: CurrentUser, package_name: str, permission: Permission) -> PackagePermissions:
    permissions = get_permissions(db, user, package_name)
    if not permissions.view:
        raise HTTPException(status_code=404, detail="Package not found")

    if not permissions.has(permission):
        raise HTTPException(
            status_code=403,
            detail=f"You do not have {permission.value} rights for package {package_name}"
        )

    return permissions


def visible_package_names(db: Session, user: CurrentUser) -> set[str] | None:
    if user.is_admin:
        return None

    names = set(PackageShareRepository.list_owned_package_names(db, user.id))
    names.update(share.package_name for share in PackageShareRepository.list_shares_for_user(db, user.id))  # type: ignore
    return names


def permissions_by_package(db: Session, user: CurrentUser) -> dict[str, PackagePermissions]:
    result = {name: ALL_PERMISSIONS for name in PackageShareRepository.list_owned_package_names(db, user.id)}
    for share in PackageShareRepository.list_shares_for_user(db, user.id):
        if share.package_name in result:
            continue
        result[share.package_name] = PackagePermissions(  # type: ignore
            view=True, execute=bool(share.can_execute), edit=bool(share.can_edit), manage=False)
    return result


def claim_or_check_deploy(db: Session, user: CurrentUser, package_name: str) -> None:
    package_exists = len(PackageRepository.list_packages(db, package_name)) > 0
    owner_id = PackageShareRepository.get_owner_id(db, package_name)

    if not package_exists and owner_id is None:
        # New package name: the deploying user becomes the owner.
        if not user.is_system:
            PackageShareRepository.set_owner(db, package_name, user.id)
        return

    if user.is_admin:
        return

    permissions = get_permissions(db, user, package_name)
    if not permissions.edit:
        raise HTTPException(
            status_code=403,
            detail=f"Package {package_name} already exists and you do not have edit rights for it"
        )


def require_task(user: CurrentUser, task_id: str, permission: Permission, db: Session) -> TaskEntity:
    task = TaskRepository().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        require(db, user, task.package.package_name, permission)  # type: ignore
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Task not found")
        raise

    return task


def can_access_task(user: CurrentUser, task_id: str, permission: Permission) -> bool:
    if user.is_admin:
        return TaskRepository().get_task(task_id) is not None

    db = next(get_db_session())
    try:
        require_task(user, task_id, permission, db)
        return True
    except HTTPException:
        return False
    finally:
        db.close()


def can_access_package(user: CurrentUser, package_name: str, permission: Permission) -> bool:
    db = next(get_db_session())
    try:
        return get_permissions(db, user, package_name).has(permission)
    finally:
        db.close()
