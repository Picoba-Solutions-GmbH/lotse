import asyncio
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.misc.task_status import TaskStatus
from src.models.async_execution_response import AsyncExecutionResponse
from src.models.execution_request import ExecutionRequest
from src.models.package_request_argument import PackageRequestArgument
from src.models.sync_execution_response import SyncExecutionResponse
from src.services.kubernetes.k8s_manager_service import K8sManagerService
from src.services.task_manager_service import TaskManagerService
from src.utils import config
from src.utils.singleton_meta import get_service

router = APIRouter(prefix="/execute", tags=["execute"])


async def execute_package(package_name: str, version: Optional[str], stage: str, arguments: list,
                          wait_for_completion: bool,
                          redirect_to_ui: bool,
                          task_manager: TaskManagerService,
                          k8s_manager_service: K8sManagerService,
                          empty_instance: bool
                          ) -> Union[SyncExecutionResponse, AsyncExecutionResponse, RedirectResponse]:
    task_id = await k8s_manager_service.execute_package_async(package_name, stage, version, arguments, empty_instance)

    if wait_for_completion:
        while True:
            task = task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task_is_not_running = task.status != TaskStatus.RUNNING and task.status != TaskStatus.INITIALIZING
            if task_is_not_running:
                if task.status == TaskStatus.FAILED:
                    raise HTTPException(status_code=400, detail=task.result['error'])  # type: ignore

                return SyncExecutionResponse(
                    success=True,
                    output=task.result['output'],  # type: ignore
                    error='',
                    task_id=task_id
                )
            await asyncio.sleep(0.1)
    elif redirect_to_ui:
        start_time = asyncio.get_running_loop().time()
        while True:
            task = task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task_is_running = task.status == TaskStatus.RUNNING and task.is_ui_app and task.ui_port
            if task_is_running:
                await asyncio.sleep(1)
                return RedirectResponse(
                    f"{config.OPENAPI_PREFIX_PATH}/proxy/{task_id}",
                    status_code=303
                )

            current_time = asyncio.get_running_loop().time()
            if current_time - start_time > 30:
                return AsyncExecutionResponse(
                    task_id=task_id,
                    message=f"Package {package_name} execution started, but UI not ready after 30 seconds",
                    status="running"
                )

            await asyncio.sleep(0.1)
    else:
        return AsyncExecutionResponse(
            task_id=task_id,
            message=f"Package {package_name} execution started",
            status="running"
        )


@router.get("/{package_name}/default/{stage}",
            response_model=Union[SyncExecutionResponse, AsyncExecutionResponse])
async def execute_package_get(
        package_name: str,
        stage: str,
        request: Request,
        task_manager: TaskManagerService = get_service(TaskManagerService),
        k8s_manager_service: K8sManagerService = get_service(K8sManagerService),
        wait_for_completion: bool = False,
        redirect_to_ui: bool = False):
    query_params = dict(request.query_params)
    arguments = [PackageRequestArgument(name=key, value=value) for key, value in query_params.items()
                 if key not in ["wait_for_completion", "redirect_to_ui"]]
    return await execute_package(
        package_name=package_name,
        version=None,
        stage=stage,
        arguments=arguments,
        wait_for_completion=wait_for_completion,
        redirect_to_ui=redirect_to_ui,
        task_manager=task_manager,
        k8s_manager_service=k8s_manager_service,
        empty_instance=False
    )


@router.get("/{package_name}/{version}/{stage}",
            response_model=Union[SyncExecutionResponse, AsyncExecutionResponse])
async def execute_versioned_package_get(
        package_name: str,
        version: str,
        stage: str,
        request: Request,
        task_manager: TaskManagerService = get_service(TaskManagerService),
        k8s_manager_service: K8sManagerService = get_service(K8sManagerService),
        wait_for_completion: bool = False,
        redirect_to_ui: bool = False):
    query_params = dict(request.query_params)
    arguments = [PackageRequestArgument(name=key, value=value) for key, value in query_params.items()
                 if key not in ["wait_for_completion"]]
    return await execute_package(
        package_name=package_name,
        version=version,
        stage=stage,
        arguments=arguments,
        wait_for_completion=wait_for_completion,
        redirect_to_ui=redirect_to_ui,
        task_manager=task_manager,
        k8s_manager_service=k8s_manager_service,
        empty_instance=False
    )


@router.post("/", response_model=Union[SyncExecutionResponse, AsyncExecutionResponse])
async def execute_package_post(
        request: ExecutionRequest,
        k8s_manager_service: K8sManagerService = get_service(K8sManagerService),
        task_manager: TaskManagerService = get_service(TaskManagerService)):
    return await execute_package(
        package_name=request.package_name,
        version=request.version,
        stage=request.stage,
        arguments=request.arguments,
        wait_for_completion=request.wait_for_completion,
        redirect_to_ui=False,
        task_manager=task_manager,
        k8s_manager_service=k8s_manager_service,
        empty_instance=False
    )


@router.post("/empty-instance", response_model=Union[SyncExecutionResponse, AsyncExecutionResponse])
async def execute_empty_instance(
        request: ExecutionRequest,
        k8s_manager_service: K8sManagerService = get_service(K8sManagerService),
        task_manager: TaskManagerService = get_service(TaskManagerService)):
    return await execute_package(
        package_name=request.package_name,
        version=request.version,
        stage=request.stage,
        arguments=request.arguments,
        wait_for_completion=request.wait_for_completion,
        redirect_to_ui=False,
        task_manager=task_manager,
        k8s_manager_service=k8s_manager_service,
        empty_instance=True
    )
