import asyncio
import logging
import os
from logging import Logger

from kubernetes import client

from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import PackageConfig
from src.services.kubernetes import pod_api_wrapper
from src.services.kubernetes.pod_executor import PodExecutor
from src.services.kubernetes.pod_file_operations import PodFileOperations
from src.services.kubernetes.pod_manager import PodManager
from src.services.package_service import PackageInfo
from src.utils.path_manager import PathManager


def setup_venv(api: client.CoreV1Api, namespace: str, pod_name: str,
               requirements_path: str, logger: Logger):
    shell_to_use = PodExecutor.get_available_shell(api, namespace, pod_name)
    exec_command = [
        shell_to_use, '-c',
        f'python -m venv /app/venv && . /app/venv/bin/activate && '
        f'pip install -r {requirements_path}'
    ]

    def line_callback(line: str) -> bool:
        try:
            logger.info(line)
        except UnicodeEncodeError:
            logger.info(line.encode('ascii', 'replace').decode('ascii'))

        return False

    exit_code = PodExecutor.run_command(api, namespace, pod_name, exec_command, line_callback)
    if exit_code is not None and exit_code != 0:
        message = f"Virtual environment setup failed with exit code {exit_code}"
        logger.error(message)
        raise RuntimeError(message)

    logger.info("Virtual environment created successfully")


def prepare_environment(v1: client.CoreV1Api,
                        namespace: str,
                        task_id: str,
                        task_logger: logging.Logger,
                        package_name: str,
                        stage: str,
                        package_info: PackageInfo,
                        package_config: PackageConfig) -> None:
    venv_path = PathManager.get_venv_path(
        package_name,
        package_info.package_entity.version,
        stage)
    if not os.path.exists(venv_path):
        os.makedirs(venv_path, exist_ok=True)

    tar_file_path = os.path.join(venv_path, "venv.tar.gz")
    if not os.path.exists(tar_file_path):
        PodManager.create_pod(v1, namespace, task_id,
                              package_info.package_entity.python_version, [], task_logger, [],
                              package_config.image, RuntimeType.PYTHON, False)
        asyncio.run(pod_api_wrapper.wait_for_pod_running(v1, namespace, task_id, task_logger))
        PodFileOperations.copy_files_to_pod(namespace, task_id, str(package_info.package_dir), "/app")
        setup_venv(v1, namespace, task_id, "/app/requirements.txt", task_logger)
        PodFileOperations.copy_file_from_pod(v1, namespace, task_id, "/app/venv",
                                             tar_file_path)
        PodManager.delete_pod(v1, namespace, task_id, task_logger)


def prepare_runtime(v1: client.CoreV1Api,
                    namespace: str,
                    task_id: str,
                    task_logger: logging.Logger,
                    package_name: str,
                    stage: str,
                    package_info: PackageInfo) -> None:
    venv_path = PathManager.get_venv_path(
        package_name,
        package_info.package_entity.version,
        stage
    )
    tar_file_path = os.path.join(venv_path, "venv.tar.gz")

    task_logger.info(f"Copying venv files to pod {task_id}")
    PodFileOperations.copy_files_to_pod(namespace, task_id, tar_file_path, "/tmp")
    task_logger.info(f"Extracting venv files in pod {task_id}")
    PodFileOperations.extract_tar_gz(v1, namespace, task_id, "/tmp/venv.tar.gz", "/app/venv")
