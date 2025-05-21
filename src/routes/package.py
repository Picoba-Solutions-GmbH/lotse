import os
import shutil
from datetime import datetime
from typing import Optional

import patoolib
import semver
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pipe import groupby
from sqlalchemy.orm import Session

from src.database.database_access import get_db_session
from src.database.models.package_entity import PackageEntity
from src.misc import constants
from src.misc.package_status import PackageStatus
from src.misc.runtime_type import RuntimeType
from src.misc.task_status import TaskStatus
from src.models.package_info import PackageDetail, PackageInfo, PackageInstance
from src.models.task_info import TaskInfo
from src.models.yaml_config import Environment, parse_config
from src.routes import authentication
from src.services.kubernetes.k8s_manager_service import K8sManagerService
from src.services.package_repository import PackageRepository
from src.services.package_service import PackageService
from src.services.task_manager_service import (TaskManagerService,
                                               map_task_entity_to_task_info)
from src.services.volume_repository import VolumeRepository
from src.utils.path_manager import PathManager
from src.utils.singleton_meta import get_service

router = APIRouter(prefix="/packages", tags=["packages"])


@router.post("/deploy")
async def deploy_package(
    package_file: UploadFile = File(...),
    config_yaml: UploadFile = File(...),
    stage=Form(..., regex=constants.stage_regex_pattern),
    set_as_default: bool = Form(False),
    disable_previous_versions: bool = Form(False),
    db_session: Session = Depends(get_db_session),
    _=Depends(authentication.require_operator_or_admin)
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
        db_session, package_config.package_name, stage, package_config.version)
    if existing_package:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Package {package_config.package_name} version {package_config.version} "
                f"already exists in {stage} environment"
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

    if package_config.runtime != RuntimeType.CONTAINER:
        package_dir = PathManager.get_package_path(package_config.package_name,
                                                   package_config.version, stage)
        os.makedirs(package_dir, exist_ok=True)
        file_path = os.path.join(package_dir, f"{package_config.package_name}.7z")

        with open(file_path, "wb") as f:
            shutil.copyfileobj(package_file.file, f)

        patoolib.extract_archive(file_path, outdir=str(package_dir))

    set_active = set_as_default or disable_previous_versions
    metadata = PackageRepository.create_package(
        db_session, package_config.package_name, package_config.version,
        package_config.python_version, stage,
        config_yaml_content, package_config.description, set_active
    )

    if disable_previous_versions:
        other_versions = PackageRepository.list_other_package_version(
            db_session, package_config.package_name, stage, package_config.version)
        for other_version in other_versions:
            venv_path = PathManager.get_venv_path(other_version.package_name,
                                                  other_version.version, other_version.stage)
            shutil.rmtree(venv_path, ignore_errors=True)
            package_path = PackageService.get_package_path(
                other_version.package_name, other_version.version, other_version.stage)
            if package_path:
                shutil.rmtree(package_path, ignore_errors=True)

        PackageRepository.delete_other_package_versions(
            db_session, package_config.package_name, stage, package_config.version)

    response_data = {
        "package_name": metadata.package_name,
        "python_version": metadata.python_version,
        "version": metadata.version,
        "stage": metadata.stage,
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
    stage: str = Form(..., regex=constants.stage_regex_pattern),
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_operator_or_admin)
):
    success = PackageRepository.set_active_package(db, package_name, version, stage)
    if not success:
        raise HTTPException(status_code=404, detail="Package not found")

    return {"message": "Package set as active successfully"}


@router.get("/list")
async def list_packages(
    package_name: Optional[str] = None,
    stage: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    packages = PackageRepository.list_packages(db, package_name, stage)

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
                "default": arg.defaultvalue
            })

        result.append({
            "package_name": package.package_name,
            "python_version": package.python_version,
            "version": package.version,
            "stage": package.stage,
            "description": package.description,
            "deployed_at": package.deployed_at.isoformat(),
            "deployment_id": package.deployment_id,
            "active": package.active,
            "environment": environment,
            "package_arguments": package_arguments,
        })

    return result


@router.delete("/{package_name}/{stage}/{version}")
async def delete_package(
    package_name: str,
    stage: str,
    version: str,
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin)
):
    package_dir = PathManager.get_package_path(package_name, version, stage)
    venv_dir = PathManager.get_venv_path(package_name, version, stage)

    success = PackageRepository.delete_package(db, package_name, version, stage)
    if success:
        if os.path.exists(package_dir):
            shutil.rmtree(package_dir, ignore_errors=True)

        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)

    return {"message": "Package deleted successfully"}


@router.get("/{stage}")
async def get_packages_by_stage(
    stage: str,
    db: Session = Depends(get_db_session),
    task_manager_service: TaskManagerService = get_service(TaskManagerService)
):
    package_infos: list[PackageInfo] = []
    packages = PackageRepository.list_packages(db, None, stage)

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
            creation_date=oldest_package
        )
        package_infos.append(package_info)

    return package_infos


@router.get("/{package_name}/{stage}")
async def get_package_by_stage(
    package_name: str,
    stage: str,
    db: Session = Depends(get_db_session),
    task_manager_service: TaskManagerService = get_service(TaskManagerService)
):
    package_details: list[PackageDetail] = []
    packages = PackageRepository.list_packages(db, package_name, stage)

    for package in packages:
        tasks_count = task_manager_service.get_tasks_count_by_deployment_id(
            package.deployment_id, [TaskStatus.RUNNING, TaskStatus.INITIALIZING])

        package_status = PackageStatus.RUNNING if tasks_count > 0 else PackageStatus.IDLE
        package_info = PackageDetail(
            name=package_name,
            status=package_status,
            instances=tasks_count,
            creation_date=datetime.now(),
            version=package.version
        )
        package_details.append(package_info)

    return package_details


@router.get("/{package_name}/{stage}/{version}")
async def get_package_by_version(
    package_name: str,
    stage: str,
    version: str,
    db: Session = Depends(get_db_session),
    task_manager_service: TaskManagerService = get_service(TaskManagerService),
    k8s_manager_service: K8sManagerService = get_service(K8sManagerService)
):
    package = PackageRepository.get_package(db, package_name, stage, version)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    tasks = task_manager_service.get_tasks_by_deployment_id(package.deployment_id, [])
    task_infos: list[TaskInfo] = []
    for task in tasks:
        task_info = map_task_entity_to_task_info(task, None)
        if task.status == TaskStatus.RUNNING or task.status == TaskStatus.INITIALIZING:
            metrics = k8s_manager_service.get_task_metrics(task.task_id)
            if metrics:
                task_info.metrics = metrics

        task_infos.append(task_info)

    task_infos.sort(key=lambda x: (x.status == TaskStatus.RUNNING, x.started_at), reverse=True)

    config_yaml_content = parse_config(package.config)
    package_arguments = []
    for arg in config_yaml_content.args:
        package_arguments.append({
            "name": arg.name,
            "default": arg.defaultvalue
        })

    package_instance = PackageInstance(
        name=package_name,
        description=package.description,
        tasks=task_infos,
        package_arguments=package_arguments,
    )

    return package_instance


@router.get("/{package_name}/{stage}/{version}/environment")
async def get_package_environment(
    package_name: str,
    stage: str,
    version: str,
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin)
):
    package = PackageRepository.get_package(db, package_name, stage, version)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    config_yaml_content = parse_config(package.config)
    environment: list[Environment] = []
    for env in config_yaml_content.environment:
        environment.append(Environment(name=env.name, value=env.value))

    return environment
