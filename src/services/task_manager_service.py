import asyncio
import logging
import os
import threading
from typing import List, Optional

from kubernetes import client, config

import src.utils.config as framework_config
from src.database.repositories.task_repository import TaskRepository
from src.database.repositories.volume_repository import VolumeRepository
from src.misc.runtime_type import RuntimeType
from src.misc.task_status import TaskStatus
from src.models.k8s.cluster import PodMetrics
from src.models.package_request_argument import PackageRequestArgument
from src.models.sync_execution_response import SyncExecutionResponse
from src.models.yaml_config import parse_config
from src.services.kubernetes import pod_api_wrapper
from src.services.kubernetes.pod_environment import PodEnvironment
from src.services.kubernetes.pod_executor import PodExecutor
from src.services.kubernetes.pod_file_operations import PodFileOperations
from src.services.kubernetes.pod_manager import PodManager
from src.services.kubernetes.pod_port_manager import PodPortManager
from src.services.kubernetes.runtimes import python_pod
from src.services.package_service import PackageService
from src.utils import global_queue_handler
from src.utils.name_generator import generate_name
from src.utils.singleton_meta import SingletonMeta
from src.utils.task_logger import TaskLogger

logger = logging.getLogger(__name__)


class TaskManagerService(metaclass=SingletonMeta):
    def __init__(self,
                 task_manager: TaskRepository):
        self.task_manager = task_manager
        self.task_logger = TaskLogger()

        if framework_config.IS_DEBUG:
            config.load_kube_config()
        else:
            config.load_incluster_config()

        self.v1 = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        self.namespace = framework_config.K8S_NAMESPACE

    def cancel_task(self, task_id: str) -> bool:
        task_logger = self.task_logger.setup_logger(task_id)
        self.task_manager.update_task_status(task_id, TaskStatus.CANCELLED, None)
        PodManager.delete_pod(self.v1, self.namespace, task_id, task_logger)
        return True

    def execute_package(
            self,
            task_id: str,
            package_name: str,
            stage: str,
            version: Optional[str],
            arguments: List[PackageRequestArgument],
            empty_instance: bool) -> bool:
        task_logger = self.task_logger.setup_logger(task_id)

        try:
            package_info = PackageService.get_package_info(package_name, stage, version)
            if package_info is None:
                raise FileNotFoundError(f"Package not found for {package_name} in stage {stage}")

            package_config = parse_config(package_info.package_entity.config)

            self.task_manager.update_task_status(
                task_id,
                TaskStatus.INITIALIZING,
                None
            )
            package_dir = package_info.package_dir

            match package_config.runtime:
                case RuntimeType.PYTHON:
                    python_pod.prepare_environment(
                        self.v1,
                        self.namespace,
                        task_id,
                        task_logger,
                        package_name,
                        stage,
                        package_info,
                        package_config
                    )

            volume_maps = VolumeRepository.get_volume_maps(package_config.volumes)
            PodManager.create_pod(self.v1, self.namespace, task_id,
                                  package_info.package_entity.python_version,
                                  package_config.environment, task_logger, volume_maps,
                                  package_config.image, package_config.runtime,
                                  empty_instance)
            asyncio.run(pod_api_wrapper.wait_for_pod_running(self.v1, self.namespace, task_id, task_logger))

            if package_config.runtime != RuntimeType.CONTAINER:
                task_logger.info(f"Copying package files to pod {task_id}")
                PodFileOperations.copy_files_to_pod(self.namespace, task_id, str(package_dir), "/app")

            match package_config.runtime:
                case RuntimeType.PYTHON:
                    python_pod.prepare_runtime(
                        self.v1,
                        self.namespace,
                        task_id,
                        task_logger,
                        package_name,
                        stage,
                        package_info
                    )

            command = []
            for arg in arguments:
                if arg.name.startswith("--"):
                    command.append(arg.name)
                    command.append(str(arg.value))
                else:
                    command.append(arg.value)

            task_logger.info(f"Executing package: {package_name}, Stage: {stage}")
            self.task_manager.update_task_status(
                task_id,
                TaskStatus.RUNNING,
                None
            )

            if package_config.runtime != RuntimeType.CONTAINER:
                if empty_instance:
                    command = ["tail", "-f", "/dev/null"]

                    def line_callback(line: str) -> bool:
                        task_logger.info(line)
                        return False

                    PodExecutor.run_command(self.v1, self.namespace, task_id, command, line_callback)
                    result = 1
                else:
                    file_name = os.path.basename(package_info.entry_point_path)
                    result = pod_api_wrapper.start_app(
                        self.v1, self.namespace, task_id,
                        file_name, command, task_logger, task_id, self.task_manager,
                        package_config.runtime
                    )
            else:
                result = asyncio.run(pod_api_wrapper.watch_pod(self.v1, self.namespace,
                                     task_id, task_logger, task_id, self.task_manager))

            return result is not None and result == 0
        except Exception as e:
            PodManager.delete_pod(self.v1, self.namespace, task_id, task_logger)
            logger.error(f"Error executing package: {str(e)}")
            return False

    def __internal_run_package(self, timeout: int, task_id: str, package_name: str,
                               stage: str, version: Optional[str], arguments: List[PackageRequestArgument],
                               empty_instance: bool):
        task_logger = self.task_logger.setup_logger(task_id)
        try:
            timer = None
            if timeout > 0:
                def kill_on_timeout():
                    task_logger.info(f"Package execution timed out after {timeout} seconds")
                    self.task_manager.kill_and_update_task(task_id, TaskStatus.TIMEOUT)
                    PodManager.delete_pod(self.v1, self.namespace, task_id, task_logger)

                timer = threading.Timer(timeout, kill_on_timeout)
                timer.daemon = True
                timer.start()

            output_lines = []
            error_lines = []
            success = self.execute_package(task_id, package_name, stage, version, arguments, empty_instance)

            if timer:
                timer.cancel()

            result = SyncExecutionResponse(
                success=success,
                task_id=task_id,
                output=''.join(output_lines),
                error=''.join(error_lines)
            )

            status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            task = self.task_manager.get_task(task_id)
            if task is None:
                raise Exception(f"Task {task_id} not found")

            if task.status == TaskStatus.CANCELLED:
                task_logger.info("Package was cancelled")
            elif task.status == TaskStatus.TIMEOUT:
                pass
            else:
                self.task_manager.update_task_status(task_id, status, result.__dict__)
                task_logger.info(f"Package execution completed with status: {status}")
        except Exception as e:
            self.task_manager.update_task_status(
                task_id,
                TaskStatus.FAILED,
                SyncExecutionResponse(
                    success=False,
                    task_id=task_id,
                    output="",
                    error=str(e)
                ).__dict__
            )
        finally:
            self.task_manager.update_task_pid(task_id, None)

    async def execute_package_async(self,
                                    package_name: str,
                                    stage: str,
                                    version: Optional[str],
                                    arguments: List[PackageRequestArgument],
                                    empty_instance: bool) -> str:

        package_info = PackageService.get_package_info(package_name, stage, version)
        if package_info is None:
            raise FileNotFoundError(f"Package {package_name} ({version}) not found in stage {stage}")

        task_id = generate_name(package_name)

        self.task_manager.add_task(task_id, package_info.package_entity.deployment_id, stage, arguments)
        parsed_config = parse_config(package_info.package_entity.config)
        if parsed_config is None:
            raise FileNotFoundError(f"Package {package_name} ({version}) not found in stage {stage}")

        timeout = (framework_config.GLOBAL_TASK_TIMEOUT_SECONDS if parsed_config.timeout is None
                   else parsed_config.timeout)

        threading.Thread(
            target=self.__internal_run_package,
            args=(timeout, task_id, package_name, stage, version, arguments, empty_instance),
            daemon=True
        ).start()

        return task_id

    async def check_and_initialize_pods(self) -> None:
        tasks = self.task_manager.get_running_tasks()
        for task in tasks:
            pod_name = task.task_id
            try:
                pod = PodManager.get_pod(self.v1, self.namespace, pod_name)
                if pod is None or pod.status.phase != "Running":
                    self.task_manager.kill_and_update_task(task.task_id, TaskStatus.FAILED)
                    continue

                task_logger = self.task_logger.setup_logger(task.task_id)
                if framework_config.IS_DEBUG and task.is_ui_app and task.original_ui_port:
                    await PodPortManager.port_forward_local(
                        self.namespace, pod_name, task_logger,
                        task.task_id, self.task_manager, task.original_ui_port)

                if task.vscode_port is not None and task.vscode_port != 0:
                    self.install_and_run_vscode_server(task.task_id)

            except Exception as e:
                logger.error(f"Error checking pod {pod_name}: {str(e)}")
                self.task_manager.kill_and_update_task(task.task_id, TaskStatus.FAILED)

        running_pods = PodManager.get_running_pods(self.v1, self.namespace)
        for pod in running_pods:
            task_of_pod = self.task_manager.get_task(pod)
            if task_of_pod is None:
                PodManager.delete_pod(self.v1, self.namespace, pod, None)
            else:
                is_task_running = (task_of_pod.status == TaskStatus.RUNNING or
                                   task_of_pod.status == TaskStatus.INITIALIZING)
                if not is_task_running:
                    task_logger = self.task_logger.setup_logger(task_of_pod.task_id)
                    PodManager.delete_pod(self.v1, self.namespace, pod, task_logger)

    def get_task_metrics(self, task_id: str) -> Optional[PodMetrics]:
        return PodManager.get_pod_metrics(self.custom_api, self.namespace, task_id)

    def get_task_logs(self, task_id: str) -> Optional[str]:
        return PodManager.get_pod_logs(self.v1, self.namespace, task_id)

    def install_ssh_server(self, task_id: str) -> bool:
        task_logger = self.task_logger.setup_logger(task_id)
        try:
            PodEnvironment.install_ssh_server(self.v1, self.namespace, task_id, "sshuser", "123456", task_logger)
            return True
        except Exception as e:
            logger.error(f"Error installing SSH server: {str(e)}")
            return False

    def install_and_run_vscode_server(self, task_id: str) -> bool:
        task_logger = self.task_logger.setup_logger(task_id)
        try:
            PodEnvironment.install_and_run_vscode_server(
                self.v1, self.namespace, task_id, task_logger)
            vs_code_port = 8080
            if framework_config.IS_DEBUG:
                async def port_forward_vscode():
                    result = await PodPortManager.port_forward(self.namespace, task_id, vs_code_port)
                    if result:
                        _, local_port = result
                        if local_port:
                            self.task_manager.update_vscode_port(task_id, int(local_port))
                task_queue = global_queue_handler.GlobalQueueHandlerSingleton.get_instance()
                task_queue.enqueue(port_forward_vscode)
            else:
                self.task_manager.update_vscode_port(task_id, vs_code_port)

            return True
        except Exception as e:
            logger.error(f"Error installing VSCode server: {str(e)}")
            return False
