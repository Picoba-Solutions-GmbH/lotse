from typing import Optional

from pydantic import BaseModel

from src.misc.task_status import TaskStatus
from src.models.metric import Metric


class TaskInfo(BaseModel):
    task_id: str
    package_name: str
    package_version: str
    status: TaskStatus
    stage: str
    hostname: str
    ip_address: str
    pid: Optional[int] = None
    message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    is_ui_app: bool = False
    ui_port: Optional[int] = None
    original_ui_port: Optional[int] = None
    vscode_port: Optional[int] = None
    metrics: Optional[Metric] = None
