import datetime
import os
import socket
from typing import List, Optional

import psutil
from sqlalchemy.orm import joinedload

from src.database.database_access import get_db_session
from src.database.models.task_entity import TaskEntity
from src.misc.task_status import TaskStatus
from src.models.sync_execution_response import SyncExecutionResponse
from src.models.task_info import TaskInfo
from src.utils.singleton_meta import SingletonMeta


def map_task_entity_to_task_info(task: TaskEntity, message: Optional[str]) -> TaskInfo:
    return TaskInfo(
        task_id=task.task_id,
        package_name=task.package.package_name,
        package_version=task.package.version,
        status=task.status,  # type: ignore
        stage=task.stage,
        pid=task.pid,
        started_at=str(task.started_at),
        finished_at=str(task.finished_at) if task.finished_at else None,
        message=message,
        hostname=task.hostname,
        ip_address=task.ip_address,
        is_ui_app=task.is_ui_app,
        ui_port=task.ui_port,
        vscode_port=task.vscode_port,
        original_ui_port=task.original_ui_port,
        metrics=None
    )


class TaskManagerService(metaclass=SingletonMeta):
    def __init__(self):
        self.hostname = self._get_hostname()
        self.ip_address = self.get_ip_address()

    def get_ip_address(self):
        return socket.gethostbyname(self.hostname)

    def _get_hostname(self):
        return os.environ.get('HOSTNAME', socket.gethostname())

    def _get_db_session(self):
        return next(get_db_session())

    def get_task(self, task_id: str) -> Optional[TaskEntity]:
        db = self._get_db_session()
        try:
            return (db.query(TaskEntity)
                    .options(joinedload(TaskEntity.package))
                    .filter(TaskEntity.task_id == task_id)
                    .first())
        finally:
            db.close()

    def add_task(self, task_id: str, deployment_id: str, stage: str) -> None:
        db = self._get_db_session()
        try:
            task = TaskEntity(
                task_id=task_id,
                deployment_id=deployment_id,
                status=TaskStatus.INITIALIZING,
                stage=stage,
                started_at=datetime.datetime.now(datetime.timezone.utc),
                result=None,
                pid=None,
                hostname=self.hostname,
                ip_address=self.ip_address
            )
            db.add(task)
            db.commit()
        finally:
            db.close()

    def update_task_pid(self, task_id: str, pid: Optional[int]) -> None:
        db = self._get_db_session()
        try:
            task = (db.query(TaskEntity)
                    .filter(TaskEntity.task_id == task_id)
                    .first())
            if task is not None:
                task.pid = pid  # type: ignore
                db.commit()
        finally:
            db.close()

    def update_task_status(self, task_id: str, status: TaskStatus, result: Optional[dict] = None) -> None:
        db = self._get_db_session()
        try:
            task = (db.query(TaskEntity)
                    .options(joinedload(TaskEntity.package))
                    .filter(TaskEntity.task_id == task_id)
                    .first())
            if task:
                task.status = status  # type: ignore
                if result is not None:
                    task.result = result  # type: ignore

                if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT]:
                    task.finished_at = datetime.datetime.now(datetime.timezone.utc),  # type: ignore

                db.commit()
        finally:
            db.close()

    def update_task_ui_info(self,
                            task_id: str,
                            is_ui_app: bool,
                            ui_ip_address: Optional[str] = None,
                            ui_port: Optional[int] = None) -> None:
        db = self._get_db_session()
        try:
            task = (db.query(TaskEntity)
                    .filter(TaskEntity.task_id == task_id)
                    .first())
            if task:
                task.is_ui_app = is_ui_app  # type: ignore
                if ui_ip_address is not None:
                    task.ui_ip_address = ui_ip_address  # type: ignore

                if ui_port is not None:
                    task.ui_port = ui_port  # type: ignore

                if task.original_ui_port is None:
                    task.original_ui_port = ui_port  # type: ignore

                db.commit()
        finally:
            db.close()

    def kill_and_update_task(self, task_id: str, task_status: TaskStatus) -> TaskInfo:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        pid = task.pid

        error = ""
        if task.status == TaskStatus.CANCELLED:
            error = "Task cancelled by user"
        success = True if task_status == TaskStatus.COMPLETED else False

        self.update_task_status(
            task_id,
            task_status,
            SyncExecutionResponse(
                success=success,
                task_id=task_id,
                output="",
                error=error
            ).__dict__
        )

        if pid:
            try:
                process = psutil.Process(pid)
                for child in process.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.kill()
            except psutil.NoSuchProcess:
                pass

        response_message = ""
        if task_status == TaskStatus.CANCELLED:
            response_message = "Task cancelled successfully"

        return map_task_entity_to_task_info(
            task,
            response_message
        )

    def list_tasks(self, stage: str) -> List[TaskInfo]:
        db = self._get_db_session()
        try:
            tasks = (db.query(TaskEntity)
                     .options(joinedload(TaskEntity.package))
                     .filter(TaskEntity.stage == stage)
                     .all())

            return [
                map_task_entity_to_task_info(
                    task,
                    "Result available" if task.result else None
                )
                for task in tasks
            ]
        finally:
            db.close()

    def get_running_tasks_of_pod(self) -> List[TaskInfo]:
        db = self._get_db_session()
        try:
            tasks = (db.query(TaskEntity)
                     .options(joinedload(TaskEntity.package))
                     .filter(
                         TaskEntity.ip_address == self.ip_address,
                         TaskEntity.status.in_([TaskStatus.RUNNING, TaskStatus.INITIALIZING])
                     )
                     .all())
            return [
                map_task_entity_to_task_info(
                    task,
                    "Result available" if task.result else None
                )
                for task in tasks
            ]
        finally:
            db.close()

    def get_running_tasks(self) -> List[TaskInfo]:
        db = self._get_db_session()
        try:
            tasks = (db.query(TaskEntity)
                     .options(joinedload(TaskEntity.package))
                     .filter(
                         TaskEntity.ip_address == self.ip_address,
                         TaskEntity.status.in_([TaskStatus.RUNNING, TaskStatus.INITIALIZING])
                     )
                     .all())
            return [
                map_task_entity_to_task_info(
                    task,
                    "Result available" if task.result else None
                )
                for task in tasks
            ]
        finally:
            db.close()

    def delete_task(self, task_id: str) -> None:
        db = self._get_db_session()
        try:
            task = (db.query(TaskEntity)
                    .filter(TaskEntity.task_id == task_id)
                    .first())
            if task:
                db.delete(task)
                db.commit()
        finally:
            db.close()

    def get_tasks_count_by_deployment_id(self, deployment_id: str, status: list[TaskStatus]) -> int:
        db = self._get_db_session()
        try:
            query = db.query(TaskEntity).filter(TaskEntity.deployment_id == deployment_id)

            if status:
                query = query.filter(TaskEntity.status.in_(status))

            return query.count()
        finally:
            db.close()

    def get_tasks_by_deployment_id(self, deployment_id: str, status: list[TaskStatus]) -> list[TaskEntity]:
        db = self._get_db_session()
        try:
            query = (db.query(TaskEntity)
                     .options(joinedload(TaskEntity.package))
                     .filter(TaskEntity.deployment_id == deployment_id))

            if status:
                query = query.filter(TaskEntity.status.in_(status))

            return query.all()
        finally:
            db.close()

    def update_vscode_port(self, task_id: str, vscode_port: int) -> None:
        db = self._get_db_session()
        try:
            task = (db.query(TaskEntity)
                    .filter(TaskEntity.task_id == task_id)
                    .first())
            if task:
                task.vscode_port = vscode_port  # type: ignore
                db.commit()
        finally:
            db.close()
