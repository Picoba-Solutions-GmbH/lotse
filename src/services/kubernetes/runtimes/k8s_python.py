import asyncio
import logging
import os

from kubernetes import client

from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import PackageConfig
from src.services.kubernetes import k8s_api
from src.services.package_service import PackageInfo
from src.utils.path_manager import PathManager


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
        k8s_api.create_pod(v1, namespace, task_id,
                           package_info.package_entity.python_version, [], task_logger, [],
                           package_config.image, RuntimeType.PYTHON)
        asyncio.run(k8s_api.wait_for_pod_running(v1, namespace, task_id, task_logger))
        k8s_api.copy_files_to_pod(namespace, task_id, package_info.package_dir, "/app")
        k8s_api.setup_venv(v1, namespace, task_id, "/app/requirements.txt", task_logger)
        k8s_api.copy_file_from_pod(v1, namespace, task_id, "/app/venv",
                                   tar_file_path, task_logger)
        k8s_api.delete_pod(v1, namespace, task_id, task_logger)


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
    k8s_api.copy_files_to_pod(namespace, task_id, tar_file_path, "/tmp")
    task_logger.info(f"Extracting venv files in pod {task_id}")
    k8s_api.extract_tar_gz(v1, namespace, task_id, "/tmp/venv.tar.gz", "/app/venv", task_logger)
