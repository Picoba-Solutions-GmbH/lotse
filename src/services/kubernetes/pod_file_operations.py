import os
import subprocess

from kubernetes import client

from src.services.kubernetes.pod_executor import PodExecutor


class PodFileOperations:
    @staticmethod
    def copy_files_to_pod(namespace: str, pod_name: str, file_to_copy: str, dest_path: str = "/app"):
        is_directory = os.path.isdir(file_to_copy)

        source_dir = os.path.dirname(file_to_copy) if not is_directory else file_to_copy
        file_name = os.path.basename(file_to_copy) if not is_directory else '.'

        kubectl_command = [
            'kubectl', 'cp',
            file_name,
            f"{namespace}/{pod_name}:{dest_path}",
        ]
        subprocess.run(kubectl_command, check=True, cwd=source_dir)

    @staticmethod
    def copy_file_from_pod(api: client.CoreV1Api, namespace: str, pod_name: str,
                           src_path: str, dest_path: str):
        tar_command = ['tar', 'czf', '/tmp/venv.tar.gz', '-C', src_path, '.']

        PodExecutor.run_command(api, namespace, pod_name, tar_command)

        is_directory = os.path.isdir(dest_path)
        directory_path = os.path.dirname(dest_path) if not is_directory else dest_path
        file_name = os.path.basename(dest_path) if not is_directory else '.'

        kubectl_command = [
            'kubectl', 'cp',
            f"{namespace}/{pod_name}:/tmp/venv.tar.gz",
            file_name
        ]
        subprocess.run(kubectl_command, check=True, cwd=directory_path)

    @staticmethod
    def extract_tar_gz(api: client.CoreV1Api, namespace: str, pod_name: str,
                       src_path: str, dest_path: str):
        tar_command = ['tar', 'xzf', src_path, '-C', dest_path]
        PodExecutor.run_command(api, namespace, pod_name, tar_command)
