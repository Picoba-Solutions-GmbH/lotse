import asyncio
import logging
import os
import threading
from typing import List, Optional

from kubernetes import client, config

import src.utils.config as framework_config
from src.misc.task_status import TaskStatus
from src.models.metric import Metric
from src.models.package_request_argument import PackageRequestArgument
from src.models.sync_execution_response import SyncExecutionResponse
from src.models.yaml_config import parse_config
from src.services.kubernetes import k8s_api
from src.services.package_service import PackageService
from src.services.task_manager_service import TaskManagerService
from src.services.volume_repository import VolumeRepository
from src.utils.name_generator import generate_name
from src.utils.singleton_meta import SingletonMeta
from src.utils.task_logger import TaskLogger
from src.utils.venv_manager import VenvManager

logger = logging.getLogger(__name__)


class K8sManagerService(metaclass=SingletonMeta):
    def __init__(self,
                 venv_manager: VenvManager,
                 task_manager: TaskManagerService):
        self.task_manager = task_manager
        self.venv_manager = venv_manager
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
        k8s_api.delete_pod(self.v1, self.namespace, task_id, task_logger)
        return True

    def execute_package(
            self,
            task_id: str,
            package_name: str,
            stage: str,
            version: Optional[str],
            arguments: List[PackageRequestArgument]) -> bool:
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

            venv_path = self.venv_manager.get_venv_path(
                package_name,
                package_info.package_entity.version,
                stage)
            if not os.path.exists(venv_path):
                os.makedirs(venv_path, exist_ok=True)

            tar_file_path = os.path.join(venv_path, "venv.tar.gz")
            if not os.path.exists(tar_file_path):
                k8s_api.create_pod(self.v1, self.namespace, task_id,
                                   package_info.package_entity.python_version, [], task_logger, [])
                asyncio.run(k8s_api.wait_for_pod_running(self.v1, self.namespace, task_id, task_logger))
                k8s_api.copy_files_to_pod(self.namespace, task_id, package_dir, "/app")
                k8s_api.setup_venv(self.v1, self.namespace, task_id, "/app/requirements.txt", task_logger)
                k8s_api.copy_file_from_pod(self.v1, self.namespace, task_id, "/app/venv",
                                           tar_file_path, task_logger)
                k8s_api.delete_pod(self.v1, self.namespace, task_id, task_logger)

            volume_maps = VolumeRepository.get_volume_maps(package_config.volumes)
            k8s_api.create_pod(self.v1, self.namespace, task_id,
                               package_info.package_entity.python_version,
                               package_config.environment, task_logger, volume_maps)
            asyncio.run(k8s_api.wait_for_pod_running(self.v1, self.namespace, task_id, task_logger))
            task_logger.info(f"Copying package files to pod {task_id}")
            k8s_api.copy_files_to_pod(self.namespace, task_id, package_dir, "/app")
            task_logger.info(f"Copying venv files to pod {task_id}")
            k8s_api.copy_files_to_pod(self.namespace, task_id, tar_file_path, "/tmp")
            task_logger.info(f"Extracting venv files in pod {task_id}")
            k8s_api.extract_tar_gz(self.v1, self.namespace, task_id, "/tmp/venv.tar.gz", "/app/venv", task_logger)

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

            file_name = os.path.basename(package_info.entry_point_path)
            package_path = f"/app/{file_name}"
            result = k8s_api.start_python_app(self.v1, self.namespace, task_id,
                                              package_path, command, task_logger, task_id, self.task_manager)

            return result is not None and result == 0
        except Exception as e:
            k8s_api.delete_pod(self.v1, self.namespace, task_id, task_logger)
            logger.error(f"Error executing package: {str(e)}")
            return False

    def __internal_run_package(self, timeout: int, task_id: str, package_name: str,
                               stage: str, version: Optional[str], arguments: List[PackageRequestArgument]):
        task_logger = self.task_logger.setup_logger(task_id)
        try:
            timer = None
            if timeout > 0:
                def kill_on_timeout():
                    task_logger.info(f"Package execution timed out after {timeout} seconds")
                    self.task_manager.kill_and_update_task(task_id, TaskStatus.TIMEOUT)
                    k8s_api.delete_pod(self.v1, self.namespace, task_id, task_logger)

                timer = threading.Timer(timeout, kill_on_timeout)
                timer.daemon = True
                timer.start()

            output_lines = []
            error_lines = []
            success = self.execute_package(task_id, package_name, stage, version, arguments)
            if success is False:
                raise Exception("Failed to start process")

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
                                    arguments: List[PackageRequestArgument]) -> str:

        package_info = PackageService.get_package_info(package_name, stage, version)
        if package_info is None:
            raise FileNotFoundError(f"Package {package_name} ({version}) not found in stage {stage}")

        task_id = generate_name(package_name)

        self.task_manager.add_task(task_id, package_info.package_entity.deployment_id, stage)
        parsed_config = parse_config(package_info.package_entity.config)
        if parsed_config is None:
            raise FileNotFoundError(f"Package {package_name} ({version}) not found in stage {stage}")

        timeout = (framework_config.GLOBAL_TASK_TIMEOUT_SECONDS if parsed_config.timeout is None
                   else parsed_config.timeout)

        threading.Thread(
            target=self.__internal_run_package,
            args=(timeout, task_id, package_name, stage, version, arguments),
            daemon=True
        ).start()

        return task_id

    async def check_and_initialize_pods(self) -> None:
        tasks = self.task_manager.get_running_tasks()
        for task in tasks:
            pod_name = task.task_id
            try:
                pod = k8s_api.get_pod(self.v1, self.namespace, pod_name)
                if pod is None or pod.status.phase != "Running":
                    self.task_manager.kill_and_update_task(task.task_id, TaskStatus.FAILED)
                    continue

                task_logger = self.task_logger.setup_logger(task.task_id)
                if framework_config.IS_DEBUG and task.is_ui_app and task.original_ui_port:
                    await k8s_api.port_forward_for_debug(
                        self.namespace, pod_name, task_logger,
                        task.task_id, self.task_manager, task.original_ui_port)

                if task.vscode_port is not None and task.vscode_port != 0:
                    k8s_api.install_and_run_vscode_server(
                        self.v1, self.namespace, pod_name, task_logger, self.task_manager)

            except Exception as e:
                logger.error(f"Error checking pod {pod_name}: {str(e)}")
                self.task_manager.kill_and_update_task(task.task_id, TaskStatus.FAILED)

        running_pods = k8s_api.get_running_pods(self.v1, self.namespace)
        for pod in running_pods:
            task_of_pod = self.task_manager.get_task(pod)
            if task_of_pod is None:
                k8s_api.delete_pod(self.v1, self.namespace, pod, None)
            else:
                is_task_running = (task_of_pod.status == TaskStatus.RUNNING or
                                   task_of_pod.status == TaskStatus.INITIALIZING)
                if not is_task_running:
                    task_logger = self.task_logger.setup_logger(task_of_pod.task_id)
                    k8s_api.delete_pod(self.v1, self.namespace, pod, task_logger)

    def get_task_metrics(self, name: str) -> Optional[Metric]:
        try:
            pod_metrics = k8s_api.get_pod_metrics(self.custom_api, self.namespace, name)
            if pod_metrics is None:
                logger.error(f"Pod {name} not found")
                return None

            cpu_usage = self.parse_k8s_cpu_resource(pod_metrics['containers'][0]['usage']['cpu'])  # type: ignore
            memory_usage = self.parse_k8s_memory_resource(
                pod_metrics['containers'][0]['usage']['memory'])  # type: ignore
            return Metric(cpu=cpu_usage, memory=memory_usage)
        except Exception as e:
            logger.error(f"Error getting pod metrics for {name}: {str(e)}")
            return None

    def parse_k8s_memory_resource(self, resource_str) -> str:
        if resource_str.endswith('Ki'):
            return f"{int(float(resource_str[:-2]) * 1024 / (1024**2))} MB"
        elif resource_str.endswith('Mi'):
            return f"{int(float(resource_str[:-2]))} MB"
        elif resource_str.endswith('Gi'):
            return f"{float(resource_str[:-2]):.2f} GB"
        elif resource_str.endswith('Ti'):
            return f"{float(resource_str[:-2]):.2f} TB"
        else:
            return f"{int(float(resource_str) / (1024**2))} MB"

    def parse_k8s_cpu_resource(self, resource_str) -> str:
        if resource_str.endswith('n'):
            return f"{float(f'{float(resource_str[:-1]) / 1e9:.3f}'.rstrip('0').rstrip('.'))} cores"
        elif resource_str.endswith('u'):
            return f"{float(f'{float(resource_str[:-1]) / 1e6:.3f}'.rstrip('0').rstrip('.'))} cores"
        elif resource_str.endswith('m'):
            return f"{float(f'{float(resource_str[:-1]):.3f}'.rstrip('0').rstrip('.'))} cores"

        return "0 cores"

    def install_ssh_server(self, task_id: str) -> bool:
        task_logger = self.task_logger.setup_logger(task_id)
        try:
            k8s_api.install_ssh_server(self.v1, self.namespace, task_id, "sshuser", "123456", task_logger)
            return True
        except Exception as e:
            logger.error(f"Error installing SSH server: {str(e)}")
            return False

    def install_and_run_vscode_server(self, task_id: str) -> bool:
        task_logger = self.task_logger.setup_logger(task_id)
        try:
            k8s_api.install_and_run_vscode_server(self.v1, self.namespace, task_id,
                                                  task_logger, self.task_manager)

            return True
        except Exception as e:
            logger.error(f"Error installing VSCode server: {str(e)}")
            return False
