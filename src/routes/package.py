import os
import shutil
from datetime import datetime

import patoolib
import semver
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pipe import groupby
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.models.package_entity import PackageEntity
from src.database.repositories.package_repository import PackageRepository
from src.database.repositories.package_share_repository import \
    PackageShareRepository
from src.database.repositories.task_repository import (
    TaskRepository, map_task_entity_to_task_info)
from src.database.repositories.user_repository import UserRepository
from src.database.repositories.volume_repository import VolumeRepository
from src.misc.package_status import PackageStatus
from src.misc.runtime_type import RuntimeType
from src.misc.task_status import TaskStatus
from src.models.package_info import (PackageDetail, PackageInfo,
                                     PackageInstance, PackageModifications)
from src.models.package_permissions import Permission
from src.models.task_info import TaskInfo
from src.models.yaml_config import Argument, Environment, parse_config
from src.routes import authentication
from src.routes.dtos.package_edit_dto import (EnvironmentVariableDto,
                                              PackageArgumentDto,
                                              PackageFileContentDto,
                                              PackageFileDto,
                                              PackageFilePathDto)
from src.services import package_access_service as access
from src.services import package_edit_service as edit
from src.services.task_manager_service import TaskManagerService
from src.utils.path_manager import PathManager
from src.utils.singleton_meta import get_service

router = APIRouter(prefix="/packages", tags=["packages"])


@router.post("/deploy")
async def deploy_package(
    package_file: UploadFile = File(...),
    config_yaml: UploadFile = File(...),
    set_as_default: bool = Form(False),
    delete_previous_versions: bool = Form(False),
    db_session: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
):
    config_yaml_bytes = await config_yaml.read()
    config_yaml_content = config_yaml_bytes.decode('utf-8')
    package_config = parse_config(config_yaml_content)

    match package_config.runtime:
        case RuntimeType.PYTHON:
            try:
                semver.parse(package_config.python_version)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Python version format. Use semver (e.g., 3.8.10)")

    existing_package = PackageRepository.get_package(
        db_session, package_config.package_name, package_config.version)
    if existing_package:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Package {package_config.package_name} version {package_config.version} "
                f"already exists"
            )
        )

    non_existing_volumes = VolumeRepository.get_non_existing_volumes(
        package_config.volumes)
    non_existing_volumes_count = len(non_existing_volumes)
    if non_existing_volumes_count > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Volume(s) {', '.join([v for v in non_existing_volumes])} "
                f"{"does" if non_existing_volumes_count == 1 else "do"} not exist in the system. "
            )
        )

    access.claim_or_check_deploy(db_session, user, package_config.package_name)

    if package_config.runtime != RuntimeType.CONTAINER:
        package_dir = PathManager.get_package_path(package_config.package_name,
                                                   package_config.version)
        os.makedirs(package_dir, exist_ok=True)
        file_path = os.path.join(package_dir, f"{package_config.package_name}.7z")

        with open(file_path, "wb") as f:
            shutil.copyfileobj(package_file.file, f)

        patoolib.extract_archive(file_path, outdir=str(package_dir))

    set_active = set_as_default or delete_previous_versions
    metadata = PackageRepository.create_package(
        db_session, package_config.package_name, package_config.version,
        package_config.python_version,
        config_yaml_content, package_config.description, set_active
    )

    if delete_previous_versions:
        other_versions = PackageRepository.list_other_package_version(
            db_session, package_config.package_name, package_config.version)
        for other_version in other_versions:
            package_dir = PathManager.get_package_path(
                other_version.package_name, other_version.version)
            venv_dir = PathManager.get_venv_path(other_version.package_name, other_version.version)
            if os.path.exists(package_dir):
                shutil.rmtree(package_dir, ignore_errors=True)

            if os.path.exists(venv_dir):
                shutil.rmtree(venv_dir, ignore_errors=True)

            edit.remove_originals(other_version.package_name, other_version.version)  # type: ignore

        PackageRepository.delete_other_package_versions(
            db_session, package_config.package_name, package_config.version)

    response_data = {
        "package_name": metadata.package_name,
        "python_version": metadata.python_version,
        "version": metadata.version,
        "description": metadata.description,
        "deployed_at": metadata.deployed_at.isoformat(),  # type: ignore
        "deployment_id": metadata.deployment_id,
        "active": metadata.active
    }

    return JSONResponse(
        status_code=201,
        content={
            "message": "Package deployed successfully",
            "metadata": response_data
        }
    )


@router.post("/set-active")
async def set_active_package(
    package_name: str = Form(...),
    version: str = Form(...),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
):
    access.require(db, user, package_name, Permission.EDIT)
    success = PackageRepository.set_active_package(db, package_name, version)
    if not success:
        raise HTTPException(status_code=404, detail="Package not found")

    return {"message": "Package set as active successfully"}


@router.get("/list")
async def list_packages(
    package_name: str | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
):
    visible_names = access.visible_package_names(db, user)
    packages = PackageRepository.list_packages(db, package_name, package_names=visible_names)
    permissions = {} if user.is_admin else access.permissions_by_package(db, user)

    result = []
    for package in packages:
        config_yaml_content = parse_config(package.config)

        environment = []
        for env in config_yaml_content.environment:
            environment.append({
                "name": env.name,
                "value": env.value
            })

        package_arguments = []
        for arg in config_yaml_content.args:
            package_arguments.append({
                "name": arg.name,
                "default": arg.defaultvalue,
                "options": arg.options,
            })

        result.append({
            "package_name": package.package_name,
            "python_version": package.python_version,
            "version": package.version,
            "description": package.description,
            "deployed_at": package.deployed_at.isoformat(),
            "deployment_id": package.deployment_id,
            "active": package.active,
            "environment": environment,
            "package_arguments": package_arguments,
            "can_execute": user.is_admin or permissions[package.package_name].execute,
        })

    return result


@router.delete("/{package_name}/{version}")
async def delete_package(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
):
    access.require(db, user, package_name, Permission.EDIT)
    package_dir = PathManager.get_package_path(package_name, version)
    venv_dir = PathManager.get_venv_path(package_name, version)

    success = PackageRepository.delete_package(db, package_name, version)
    if success:
        if os.path.exists(package_dir):
            shutil.rmtree(package_dir, ignore_errors=True)

        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)

        edit.remove_originals(package_name, version)

    return {"message": "Package deleted successfully"}


@router.get("/")
async def get_packages_by_stage(
    db: Session = Depends(get_db_session),
    task_manager_service: TaskRepository = get_service(TaskRepository),
    user: CurrentUser = Depends(authentication.require_user)
):
    package_infos: list[PackageInfo] = []
    visible_names = access.visible_package_names(db, user)
    packages = PackageRepository.list_packages(db, None, package_names=visible_names)
    permissions = {} if user.is_admin else access.permissions_by_package(db, user)
    owner_map = PackageShareRepository.get_owner_map(db)
    user_names = {u.id: u.name for u in UserRepository.list_users(db)}

    # pylint: disable=E1120
    grouped_packages: list[tuple[str, list[PackageEntity]]] = packages | groupby(lambda x: x.package_name)

    for package_name, group in grouped_packages:
        deployments = [package for package in group]
        deployment_ids = [deployment.deployment_id for deployment in deployments]
        deployment_dates = [deployment.deployed_at for deployment in deployments]

        running_instances = 0
        for deployment_id in deployment_ids:
            tasks_count = task_manager_service.get_tasks_count_by_deployment_id(
                deployment_id, [TaskStatus.RUNNING, TaskStatus.INITIALIZING])
            running_instances += tasks_count

        package_status = PackageStatus.RUNNING if running_instances > 0 else PackageStatus.IDLE
        oldest_package = min(deployment_dates)
        package_info = PackageInfo(
            name=package_name,
            status=package_status,
            instances=running_instances,
            creation_date=oldest_package,
            owner=user_names.get(owner_map.get(package_name)),  # type: ignore
            permissions=access.ALL_PERMISSIONS if user.is_admin else permissions[package_name]
        )
        package_infos.append(package_info)

    return package_infos


@router.get("/{package_name}")
async def get_package_by_stage(
    package_name: str,
    db: Session = Depends(get_db_session),
    task_manager_service: TaskRepository = get_service(TaskRepository),
    user: CurrentUser = Depends(authentication.require_user)
):
    access.require(db, user, package_name, Permission.VIEW)
    package_details: list[PackageDetail] = []
    packages = PackageRepository.list_packages(db, package_name)

    for package in packages:
        tasks_count = task_manager_service.get_tasks_count_by_deployment_id(
            package.deployment_id, [TaskStatus.RUNNING, TaskStatus.INITIALIZING])

        package_status = PackageStatus.RUNNING if tasks_count > 0 else PackageStatus.IDLE
        package_info = PackageDetail(
            name=package_name,
            status=package_status,
            instances=tasks_count,
            creation_date=package.deployed_at,
            version=package.version,
            is_default=package.active,
            is_modified=package.is_modified
        )
        package_details.append(package_info)

    return package_details


@router.get("/{package_name}/{version}")
async def get_package_by_version(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    task_repository: TaskRepository = get_service(TaskRepository),
    task_manager_service: TaskManagerService = get_service(TaskManagerService),
    user: CurrentUser = Depends(authentication.require_user)
):
    permissions = access.require(db, user, package_name, Permission.VIEW)
    package = PackageRepository.get_package(db, package_name, version)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    tasks = task_repository.get_tasks_by_deployment_id(package.deployment_id, [])
    task_infos: list[TaskInfo] = []
    for task in tasks:
        task_info = map_task_entity_to_task_info(task, None)
        if task.status == TaskStatus.RUNNING or task.status == TaskStatus.INITIALIZING:
            metrics = task_manager_service.get_task_metrics(task.task_id)
            if metrics:
                task_info.metrics = metrics

        task_infos.append(task_info)

    task_infos.sort(key=lambda x: (x.status == TaskStatus.RUNNING, x.started_at), reverse=True)

    config_yaml_content = parse_config(package.config)
    package_arguments = []
    for arg in config_yaml_content.args:
        package_arguments.append({
            "name": arg.name,
            "default": arg.defaultvalue,
            "options": arg.options,
        })

    package_instance = PackageInstance(
        name=package_name,
        description=package.description or "",
        tasks=task_infos,
        package_arguments=package_arguments,
        is_default=package.active,
        permissions=permissions,
        runtime=config_yaml_content.runtime.value if config_yaml_content.runtime else None,
        has_files=PathManager.get_package_path(package_name, version).is_dir(),
        modifications=_modifications_of(package),
    )

    return package_instance


@router.get("/{package_name}/{version}/environment")
async def get_package_environment(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
):
    access.require(db, user, package_name, Permission.EDIT)
    package = PackageRepository.get_package(db, package_name, version)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    config_yaml_content = parse_config(package.config)
    environment: list[Environment] = []
    for env in config_yaml_content.environment:
        environment.append(Environment(name=env.name, value=env.value))

    return environment


@router.post("/{package_name}/{version}/default")
async def set_default_package(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
):
    access.require(db, user, package_name, Permission.EDIT)
    package = PackageRepository.get_package(db, package_name, version)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    PackageRepository.set_active_package(db, package_name, version)

    return {"message": "Package set as default successfully"}


def _get_package_or_404(db: Session, package_name: str, version: str) -> PackageEntity:
    package = PackageRepository.get_package(db, package_name, version)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


def _modifications_of(package: PackageEntity) -> PackageModifications:
    return PackageModifications(
        is_modified=package.is_modified,
        config_modified=package.config_modified,
        modified_files=list(package.modified_files or []),  # type: ignore
        modified_at=package.modified_at,  # type: ignore
    )


@router.put("/{package_name}/{version}/environment")
async def update_package_environment(
    package_name: str,
    version: str,
    environment: list[EnvironmentVariableDto],
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> PackageModifications:
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)

    config = edit.build_config_with_environment(
        package, [Environment(name=env.name, value=env.value) for env in environment])
    PackageRepository.update_config(db, package, config)
    return _modifications_of(package)


@router.get("/{package_name}/{version}/arguments")
async def get_package_arguments(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> list[PackageArgumentDto]:
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)
    return [PackageArgumentDto(name=arg.name, default=arg.defaultvalue, options=arg.options)
            for arg in parse_config(package.config).args]  # type: ignore


@router.put("/{package_name}/{version}/arguments")
async def update_package_arguments(
    package_name: str,
    version: str,
    arguments: list[PackageArgumentDto],
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> PackageModifications:
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)

    config = edit.build_config_with_arguments(
        package, [Argument(name=arg.name, defaultvalue=arg.default, options=arg.options) for arg in arguments])
    PackageRepository.update_config(db, package, config)
    return _modifications_of(package)


@router.post("/{package_name}/{version}/config/revert")
async def revert_package_config(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> PackageModifications:
    """Restores the environment variables and arguments as they were deployed."""
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)
    PackageRepository.revert_config(db, package)
    return _modifications_of(package)


@router.get("/{package_name}/{version}/files")
async def list_package_files(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> list[PackageFileDto]:
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)
    return [PackageFileDto(**f) for f in edit.list_editable_files(package)]


@router.get("/{package_name}/{version}/files/content")
async def get_package_file_content(
    package_name: str,
    version: str,
    path: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> PackageFileContentDto:
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)
    full_path, relative = edit.resolve_editable_file(package, path)
    return PackageFileContentDto(path=relative, content=edit.read_file(full_path))


@router.put("/{package_name}/{version}/files/content")
async def update_package_file_content(
    package_name: str,
    version: str,
    file: PackageFileContentDto,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> PackageModifications:
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)
    full_path, relative = edit.resolve_editable_file(package, file.path)
    if edit.write_file(package, full_path, relative, file.content):
        if edit.matches_original(package, full_path, relative):
            # edited back to the deployed content, the file is no longer modified
            edit.revert_file(package, relative)
            PackageRepository.unmark_file_modified(db, package, relative)
        else:
            PackageRepository.mark_file_modified(db, package, relative)
    return _modifications_of(package)


@router.post("/{package_name}/{version}/files/revert")
async def revert_package_file(
    package_name: str,
    version: str,
    file: PackageFilePathDto,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> PackageModifications:
    """Restores a file as it was deployed."""
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)
    relative = edit.revert_file(package, file.path)
    PackageRepository.unmark_file_modified(db, package, relative)
    return _modifications_of(package)


@router.post("/{package_name}/{version}/revert")
async def revert_package(
    package_name: str,
    version: str,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_user)
) -> PackageModifications:
    """Restores environment variables, arguments and all edited files as they were deployed."""
    access.require(db, user, package_name, Permission.EDIT)
    package = _get_package_or_404(db, package_name, version)
    PackageRepository.revert_config(db, package)

    failed: list[str] = []
    for relative in list(package.modified_files or []):  # type: ignore
        try:
            edit.revert_file(package, relative)
            PackageRepository.unmark_file_modified(db, package, relative)
        except HTTPException:
            failed.append(relative)

    if failed:
        raise HTTPException(status_code=409,
                            detail=f"Could not restore: {', '.join(failed)}. No original version is available.")
    return _modifications_of(package)
