from pydantic import BaseModel

from src.misc.task_status import TaskStatus
from src.models.k8s.cluster import PodMetrics
from src.models.package_request_argument import PackageRequestArgument


class TaskInfo(BaseModel):
    task_id: str
    package_name: str
    package_version: str
    status: TaskStatus
    hostname: str
    ip_address: str
    pid: int | None = None
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    is_ui_app: bool = False
    ui_port: int | None = None
    original_ui_port: int | None = None
    vscode_port: int | None = None
    metrics: PodMetrics | None = None
    arguments: list[PackageRequestArgument] = []
