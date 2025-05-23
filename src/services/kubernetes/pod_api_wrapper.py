import asyncio
import re
from logging import Logger
from typing import List, Optional

from kubernetes import client

from src.database.repositories.task_repository import TaskRepository
from src.misc.runtime_type import RuntimeType
from src.misc.task_status import TaskStatus
from src.models.sync_execution_response import SyncExecutionResponse
from src.utils import config

from .pod_executor import PodExecutor
from .pod_manager import PodManager
from .pod_port_manager import PodPortManager


async def wait_for_pod_running(api: client.CoreV1Api, namespace: str, pod_name: str,
                               task_logger: Logger):
    while True:
        pod = PodManager.get_pod(api, namespace, pod_name)
        if pod and pod.status.phase == 'Running':  # type: ignore
            return True

        # type: ignore
        task_logger.info(f"Waiting for pod to be running... Current status: {pod.status.phase if pod else 'Unknown'}")
        await asyncio.sleep(1)


async def check_container_exists(api: client.CoreV1Api, namespace: str, pod_name: str) -> bool:
    pod = PodManager.get_pod(api, namespace, pod_name)
    if pod and pod.status.container_statuses:  # type: ignore
        return all(container.ready for container in pod.status.container_statuses)  # type: ignore
    return False


async def match_port(pod_name: str, line: str, api: client.CoreV1Api,
                     namespace: str, task_logger: Logger, task_id: str,
                     task_manager: TaskRepository) -> bool:
    try:
        match = re.search(
            r'((?:\d{1,3}\.){3}\d{1,3}|(?:\[?[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4}){7}\]?)):(\d+)', line)
        if match:
            url = match.group(1)
            port = match.group(2)
            pod = PodManager.get_pod(api, namespace, pod_name)
            task_logger.info(f"Detected URL: {url}, Port: {port}")
            task_manager.update_task_ui_info(
                task_id, True, pod.status.pod_ip, int(port))  # type: ignore

            if config.IS_DEBUG:
                await PodPortManager.port_forward_local(namespace, pod_name, task_logger,
                                                        task_id, task_manager, int(port))
            return True
    except Exception:
        pass
    return False


async def watch_pod(api: client.CoreV1Api, namespace: str, pod_name: str,
                    task_logger: Logger, task_id: str, task_manager: TaskRepository) -> Optional[int]:
    port_matched = False
    while True:
        container_exists = await check_container_exists(api, namespace, pod_name)
        if container_exists:
            if not port_matched:
                logs = PodManager.get_pod_logs(api, namespace, pod_name)
                port_matched = await match_port(
                    pod_name, logs, api, namespace, task_logger, task_id, task_manager)

            await asyncio.sleep(0.1)
        else:
            PodManager.delete_pod(api, namespace, pod_name, task_logger)
            return 0


def start_app(api: client.CoreV1Api, namespace: str, pod_name: str, entry_point: str,
              args: List[str], task_logger: Logger, task_id: str, task_manager: TaskRepository,
              runtime: Optional[RuntimeType] = RuntimeType.PYTHON) -> Optional[int]:
    pre_start_command = None
    match runtime:
        case RuntimeType.PYTHON:
            pre_start_command = f". venv/bin/activate && python -u {entry_point}"
        case RuntimeType.BINARY:
            pre_start_command = f"chmod +x {entry_point} && ./{entry_point}"

    shell = PodExecutor.get_available_shell(api, namespace, pod_name)
    exec_command = [shell, '-c', f'cd /app && {pre_start_command} {" ".join(args)}']

    exit_code = None

    try:
        def line_callback(line: str) -> bool:
            port_matched = False
            task_logger.info(line)
            if not port_matched:
                port_matched = asyncio.run(match_port(
                    pod_name, line, api, namespace, task_logger, task_id, task_manager))
            return False

        exit_code = PodExecutor.run_command(api, namespace, pod_name, exec_command, line_callback)
    finally:
        task = task_manager.get_task(task_id)
        if task is not None and (task.status == TaskStatus.CANCELLED):
            exit_code = 0
        else:
            PodManager.delete_pod(api, namespace, pod_name, task_logger)

            if exit_code is not None and exit_code != 0:
                task_logger.info(f"Package execution failed with exit code {exit_code}")
                task_manager.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    SyncExecutionResponse(
                        success=False,
                        task_id=task_id,
                        output="",
                        error=f"Package execution failed with exit code {exit_code}"
                    ).__dict__
                )

    task_logger.info("Application finished")
    return exit_code
