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


class PackageInstance(BaseModel):
    name: str
    description: str
    tasks: list[TaskInfo]
    package_arguments: list[dict] = []
    is_default: bool = False
    permissions: PackagePermissions | None = None
