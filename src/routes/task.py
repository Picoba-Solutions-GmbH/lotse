import asyncio
import json
import logging

import psutil
from aiohttp import ClientSession
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException,
                     WebSocket, WebSocketDisconnect)
from fastapi.websockets import WebSocketState
from kubernetes.stream import stream

from src.misc.runtime_type import RuntimeType
from src.misc.task_status import TaskStatus
from src.models.async_execution_response import AsyncExecutionResponse
from src.models.yaml_config import parse_config
from src.routes import authentication
from src.services.kubernetes import k8s_api
from src.services.kubernetes.k8s_manager_service import K8sManagerService
from src.services.task_manager_service import TaskManagerService
from src.utils.singleton_meta import get_service
from src.utils.task_logger import TaskLogger

logger = logging.getLogger(__name__)
task_logger = TaskLogger()

router = APIRouter(prefix="/task", tags=["task"])


@router.get("/status/{task_id}")
async def get_task_status(
        task_id: str,
        task_manager: TaskManagerService = get_service(TaskManagerService)):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_is_not_running = task.status != TaskStatus.RUNNING and task.status != TaskStatus.INITIALIZING
    return task.result if task_is_not_running else AsyncExecutionResponse(
        task_id=task_id,
        message=f"Package {task.package.package_name} is still running",
        status=task.status,
    )


@router.delete("/{task_id}")
async def delete_task(
        task_id: str,
        task_manager: TaskManagerService = get_service(TaskManagerService),
        _=Depends(authentication.require_operator_or_admin)):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.RUNNING or task.status == TaskStatus.INITIALIZING:
        raise HTTPException(status_code=400, detail="Cannot delete running or initializing task")
    task_manager.delete_task(task_id)
    return {"message": "Task deleted"}


@router.post("/{task_id}/cancel")
async def cancel_task(
        task_id: str,
        task_manager: TaskManagerService = get_service(TaskManagerService),
        k8s_manager_service=get_service(K8sManagerService),
        _=Depends(authentication.require_operator_or_admin)):
    try:
        task = task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status != TaskStatus.RUNNING and task.status != TaskStatus.INITIALIZING:
            raise HTTPException(status_code=400, detail=f"Task cannot be cancelled (status: {task.status})")

        current_pod_ip = task_manager.get_ip_address()
        if task.ip_address == current_pod_ip:
            return k8s_manager_service.cancel_task(task_id)
        else:
            try:
                async with ClientSession() as session:
                    async with session.post(f"http://{task.ip_address}:8000/task/{task_id}/cancel") as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            logger.error(f"Error cancelling task: {error_text}")
                            return k8s_manager_service.cancel_task(task_id)
            except Exception as e:
                logger.error(f"Error cancelling task: {str(e)}")
                return k8s_manager_service.cancel_task(task_id)
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.error(f"Error cancelling task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


@router.get("s/{stage}")
async def list_tasks(stage: str, task_manager: TaskManagerService = get_service(TaskManagerService)):
    response = task_manager.list_tasks(stage)
    return response


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: str,
    task_manager: TaskManagerService = get_service(TaskManagerService),
    k8s_service: K8sManagerService = get_service(K8sManagerService)
):
    task = task_manager.get_task(task_id)
    config_yaml_content = parse_config(task.package.config)  # type: ignore
    is_container_runtime = config_yaml_content.runtime == RuntimeType.CONTAINER

    logs = task_logger.get_logs(task_id)

    if is_container_runtime:
        pod_logs = k8s_service.get_logs(task_id)
        if pod_logs:
            logs.append(pod_logs)

    logs.reverse()

    return {"logs": logs}


@router.websocket("/{task_id}/terminal")
async def terminal_websocket(
    websocket: WebSocket,
    task_id: str,
    task_manager: TaskManagerService = get_service(TaskManagerService),
    k8s_service: K8sManagerService = get_service(K8sManagerService)
):
    resp = None
    output_task = None

    try:
        await websocket.accept()

        task = task_manager.get_task(task_id)
        if not task:
            await websocket.close(code=4004, reason="Task not found")
            return
        if task.status != TaskStatus.RUNNING:
            await websocket.close(code=4003, reason="Task is not running")
            return

        exec_command = k8s_api.get_available_shell(k8s_service.v1, k8s_service.namespace, task_id)

        resp = stream(
            k8s_service.v1.connect_get_namespaced_pod_exec,
            task_id,
            k8s_service.namespace,
            command=exec_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=True,
            _preload_content=False
        )

        async def read_output():
            try:
                while True:
                    if resp.peek_stdout():
                        output = resp.read_stdout()
                        await websocket.send_text(output)
                    if resp.peek_stderr():
                        error = resp.read_stderr()
                        await websocket.send_text(error)
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error in terminal output stream: {str(e)}")

        output_task = asyncio.create_task(read_output())

        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                if data.get("type") == "resize":
                    cols = data.get("cols", 80)
                    rows = data.get("rows", 24)
                    resp.write_channel(4, json.dumps({"Width": cols, "Height": rows}).encode())
                    continue
            except Exception:
                pass

            resp.write_stdin(message)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.error(f"Terminal WebSocket error: {str(e)}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=4002, reason=str(e))
    finally:
        if output_task:
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass

        if resp and resp.is_open():
            resp.close()

        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()


@router.post("/{task_id}/install-ssh")
async def install_ssh_server(
        task_id: str,
        k8s_service: K8sManagerService = get_service(K8sManagerService),
        _=Depends(authentication.require_operator_or_admin)):
    tasks = BackgroundTasks()
    tasks.add_task(k8s_service.install_ssh_server, task_id)
    await tasks()
    return {"message": "SSH server installation started"}


@router.post("/{task_id}/run-vscode-server")
async def install_and_run_vscode_server(
        task_id: str,
        k8s_service: K8sManagerService = get_service(K8sManagerService),
        _=Depends(authentication.require_operator_or_admin)):
    tasks = BackgroundTasks()
    tasks.add_task(k8s_service.install_and_run_vscode_server, task_id)
    await tasks()
    return {"message": "VSCode server run started"}
