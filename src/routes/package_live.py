import os
import shutil
import uuid
from datetime import datetime
from typing import Union

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, update
from sqlalchemy.orm import Session

from src.database.database_access import get_db_session
from src.database.models.package_entity import PackageEntity
from src.database.repositories.task_repository import TaskRepository
from src.models.async_execution_response import AsyncExecutionResponse
from src.models.live_package import LivePackage, LivePackageArgument, LivePackageInfo, LiveRunRequest
from src.models.sync_execution_response import SyncExecutionResponse
from src.routes import authentication
from src.routes.execute import execute_package
from src.services.task_manager_service import TaskManagerService
from src.utils.path_manager import PathManager
from src.utils.singleton_meta import get_service

router = APIRouter(prefix="/packages/live", tags=["live-code"])

LIVE_VERSION = "live"


def _get_live_dir(package_name: str) -> str:
    return str(PathManager.get_package_path(package_name, LIVE_VERSION))


def _generate_config_yaml(pkg: LivePackage) -> str:
    args = [{"name": a.name, "defaultvalue": a.default} for a in pkg.package_arguments]
    return yaml.dump(
        {
            "package_name": pkg.package_name,
            "entrypoint": "main.py",
            "version": LIVE_VERSION,
            "python_version": pkg.python_version,
            "runtime": "python",
            "args": args,
            "environment": [],
            "volumes": [],
        },
        default_flow_style=False,
    )


def _find_entity(db_session: Session, name: str) -> PackageEntity | None:
    return (
        db_session.query(PackageEntity)
        .filter(
            and_(
                PackageEntity.package_name == name,
                PackageEntity.version == LIVE_VERSION,
                PackageEntity.deleted.is_(False),
            )
        )
        .first()
    )


@router.get("", response_model=list[LivePackageInfo])
async def list_live_packages(db_session: Session = Depends(get_db_session)):
    entities = (
        db_session.query(PackageEntity)
        .filter(
            and_(
                PackageEntity.version == LIVE_VERSION,
                PackageEntity.deleted.is_(False),
            )
        )
        .all()
    )
    return [
        LivePackageInfo(
            package_name=e.package_name,
            python_version=e.python_version,
            last_modified=e.deployed_at.isoformat() if e.deployed_at else None,
        )
        for e in entities
    ]


@router.get("/{name}", response_model=LivePackage)
async def get_live_package(name: str, db_session: Session = Depends(get_db_session)):
    entity = _find_entity(db_session, name)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Live package '{name}' not found")

    package_dir = _get_live_dir(name)
    if not os.path.exists(package_dir):
        raise HTTPException(
            status_code=404, detail=f"Live package '{name}' files not found on disk"
        )

    files = []
    for filename in sorted(os.listdir(package_dir)):
        if filename.endswith(".py") or filename == "requirements.txt":
            with open(os.path.join(package_dir, filename), "r", encoding="utf-8") as f:
                files.append({"name": filename, "content": f.read()})

    config_data = yaml.safe_load(entity.config) if entity.config else {}
    args = [
        LivePackageArgument(name=a["name"], default=a.get("defaultvalue", ""))
        for a in config_data.get("args", [])
    ]
    return LivePackage(
        package_name=entity.package_name,
        python_version=entity.python_version,
        files=files,
        package_arguments=args,
    )


@router.post("", status_code=201)
async def save_live_package(
    pkg: LivePackage,
    db_session: Session = Depends(get_db_session),
    _=Depends(authentication.require_operator_or_admin),
):
    package_dir = _get_live_dir(pkg.package_name)
    os.makedirs(package_dir, exist_ok=True)

    req_path = os.path.join(package_dir, "requirements.txt")

    old_requirements: str | None = None
    if os.path.exists(req_path):
        with open(req_path, "r", encoding="utf-8") as f:
            old_requirements = f.read()

    for file in pkg.files:
        safe_name = os.path.basename(file.name)
        with open(os.path.join(package_dir, safe_name), "w", encoding="utf-8") as f:
            f.write(file.content)

    incoming_names = {os.path.basename(f.name) for f in pkg.files}
    for existing_file in os.listdir(package_dir):
        if existing_file.endswith(".py") or existing_file == "requirements.txt":
            if existing_file not in incoming_names:
                os.remove(os.path.join(package_dir, existing_file))

    if not os.path.exists(req_path):
        with open(req_path, "w", encoding="utf-8") as f:
            pass

    new_req_file = next((f for f in pkg.files if os.path.basename(f.name) == "requirements.txt"), None)
    new_requirements = new_req_file.content if new_req_file else ""
    if old_requirements is None or old_requirements.strip() != new_requirements.strip():
        venv_path = PathManager.get_venv_path(pkg.package_name, LIVE_VERSION)
        tar_path = os.path.join(str(venv_path), "venv.tar.gz")
        if os.path.exists(tar_path):
            os.remove(tar_path)

    config_yaml = _generate_config_yaml(pkg)
    existing = _find_entity(db_session, pkg.package_name)
    if existing:
        db_session.execute(
            update(PackageEntity)  # type: ignore
            .where(PackageEntity.deployment_id == existing.deployment_id)
            .values(
                python_version=pkg.python_version,
                config=config_yaml,
                deployed_at=datetime.now(),
            )
        )
    else:
        db_session.add(
            PackageEntity(
                deployment_id=str(uuid.uuid4()),
                package_name=pkg.package_name,
                python_version=pkg.python_version,
                version=LIVE_VERSION,
                description="Live coding package",
                deployed_at=datetime.now(),
                active=True,
                config=config_yaml,
            )
        )
    db_session.commit()
    return {"message": "Live package saved successfully"}


@router.delete("/{name}")
async def delete_live_package(
    name: str,
    db_session: Session = Depends(get_db_session),
    _=Depends(authentication.require_operator_or_admin),
):
    entity = _find_entity(db_session, name)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Live package '{name}' not found")

    db_session.execute(
        update(PackageEntity)  # type: ignore
        .where(PackageEntity.deployment_id == entity.deployment_id)
        .values(deleted=True)
    )
    db_session.commit()

    package_dir = _get_live_dir(name)
    if os.path.exists(package_dir):
        shutil.rmtree(package_dir, ignore_errors=True)

    return {"message": "Live package deleted successfully"}


@router.post("/{name}/run", response_model=Union[SyncExecutionResponse, AsyncExecutionResponse])
async def run_live_package(
    name: str,
    run_request: LiveRunRequest,
    task_manager: TaskRepository = get_service(TaskRepository),
    k8s_manager_service: TaskManagerService = get_service(TaskManagerService),
    _=Depends(authentication.require_operator_or_admin),
):
    return await execute_package(
        package_name=name,
        version=LIVE_VERSION,
        arguments=run_request.arguments,
        wait_for_completion=run_request.wait_for_completion,
        redirect_to_ui=False,
        task_manager=task_manager,
        k8s_manager_service=k8s_manager_service,
        empty_instance=False,
    )
