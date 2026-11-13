from datetime import datetime

from pydantic import BaseModel

from src.misc.package_status import PackageStatus
from src.models.package_permissions import PackagePermissions
from src.models.task_info import TaskInfo


class PackageInfo(BaseModel):
    name: str
    status: PackageStatus
    instances: int = 0
    creation_date: datetime
    owner: str | None = None
    permissions: PackagePermissions | None = None


class PackageDetail(PackageInfo):
    version: str
    is_default: bool = False
    is_modified: bool = False
    # Git tag and commit, for versions deployed by a Git source
    source_ref: str | None = None
    source_commit: str | None = None


class PackageModifications(BaseModel):
    is_modified: bool = False
    config_modified: bool = False
    modified_files: list[str] = []
    modified_at: datetime | None = None


class PackageInstance(BaseModel):
    name: str
    description: str
    tasks: list[TaskInfo]
    package_arguments: list[dict] = []
    is_default: bool = False
    permissions: PackagePermissions | None = None
    runtime: str | None = None
    has_files: bool = False
    modifications: PackageModifications = PackageModifications()
