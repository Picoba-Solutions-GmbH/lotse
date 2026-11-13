"""Deploying a package version. Shared by the upload endpoint and the Git sync."""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import semver
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import CurrentUser
from src.database.models.package_entity import PackageEntity
from src.database.repositories.package_repository import PackageRepository
from src.database.repositories.volume_repository import VolumeRepository
from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import PackageConfig, parse_config
from src.services import package_access_service as access
from src.services import package_edit_service as edit
from src.utils.path_manager import PathManager

# Writes the package files into the (empty) package directory
PackagePopulator = Callable[[Path, PackageConfig], None]


@dataclass(frozen=True)
class DeploymentSource:
    """Where a version came from, if it was not uploaded."""
    type: str  # "git" or "image"
    source_id: str
    ref: str
    commit: str


def validate_config(package_config: PackageConfig) -> None:
    if not package_config.package_name:
        raise HTTPException(status_code=400, detail="config.yaml has no package_name")
    if not package_config.version:
        raise HTTPException(status_code=400, detail="config.yaml has no version")

    match package_config.runtime:
        case RuntimeType.PYTHON:
            try:
                semver.parse(package_config.python_version)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid Python version format. Use semver (e.g., 3.8.10)")


def deploy_package(
    db: Session,
    user: CurrentUser,
    config_text: str,
    populate: PackagePopulator,
    set_active: bool,
    delete_previous_versions: bool,
    source: DeploymentSource | None = None,
) -> PackageEntity:
    package_config = parse_config(config_text)
    validate_config(package_config)

    existing_package = PackageRepository.get_package(db, package_config.package_name, package_config.version)
    if existing_package:
        raise HTTPException(
            status_code=409,
            detail=f"Package {package_config.package_name} version {package_config.version} already exists"
        )

    non_existing_volumes = VolumeRepository.get_non_existing_volumes(package_config.volumes)
    if non_existing_volumes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Volume(s) {', '.join(non_existing_volumes)} "
                f"{'does' if len(non_existing_volumes) == 1 else 'do'} not exist in the system. "
            )
        )

    access.claim_or_check_deploy(db, user, package_config.package_name)

    if package_config.runtime != RuntimeType.CONTAINER:
        package_dir = PathManager.get_package_path(package_config.package_name, package_config.version)
        os.makedirs(package_dir, exist_ok=True)
        try:
            populate(package_dir, package_config)
        except Exception:
            # don't leave half written files behind, they would be picked up by a later deployment
            shutil.rmtree(package_dir, ignore_errors=True)
            raise

    set_active = set_active or delete_previous_versions
    metadata = PackageRepository.create_package(
        db, package_config.package_name, package_config.version,
        package_config.python_version,
        config_text, package_config.description, set_active,
        source_type=source.type if source else None,
        source_id=source.source_id if source else None,
        source_ref=source.ref if source else None,
        source_commit=source.commit if source else None,
    )

    if delete_previous_versions:
        delete_other_versions(db, package_config.package_name, package_config.version)

    return metadata


def delete_other_versions(db: Session, package_name: str, version: str) -> None:
    for other_version in PackageRepository.list_other_package_version(db, package_name, version):
        package_dir = PathManager.get_package_path(other_version.package_name, other_version.version)  # type: ignore
        venv_dir = PathManager.get_venv_path(other_version.package_name, other_version.version)  # type: ignore
        if os.path.exists(package_dir):
            shutil.rmtree(package_dir, ignore_errors=True)

        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)

        edit.remove_originals(other_version.package_name, other_version.version)  # type: ignore

    PackageRepository.delete_other_package_versions(db, package_name, version)
