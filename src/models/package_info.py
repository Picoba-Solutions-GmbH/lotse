from datetime import datetime

from pydantic import BaseModel

from src.misc.package_status import PackageStatus
from src.models.task_info import TaskInfo


class PackageInfo(BaseModel):
    name: str
    status: PackageStatus
    instances: int = 0
    creation_date: datetime


class PackageDetail(PackageInfo):
    version: str


class PackageInstance(BaseModel):
    name: str
    description: str
    tasks: list[TaskInfo]
    package_arguments: list[dict] = []
