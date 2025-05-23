import os
import threading
from logging import Logger
from typing import Any, List, Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

from src.misc.runtime_type import RuntimeType
from src.models.k8s.cluster import PodMetrics
from src.models.k8s.volume_map import VolumeMap
from src.models.yaml_config import Environment
from src.services.kubernetes.pod_port_manager import PodPortManager
from src.utils import config

from .pod_resource_parser import PodResourceParser

k8s_api_lock = threading.Lock()


class PodManager:
    @staticmethod
    def get_pod(api: client.CoreV1Api, namespace: str, pod_name: str) -> Optional[Any]:
        try:
            with k8s_api_lock:
                pod = api.read_namespaced_pod(name=pod_name, namespace=namespace)
                return pod
        except ApiException as e:
            if e.status == 404:
                return None
            else:
                raise

    @staticmethod
    def get_running_pods(api: client.CoreV1Api, namespace: str) -> List[str]:
        try:
            with k8s_api_lock:
                pods = api.list_namespaced_pod(namespace=namespace, label_selector="app=lotse-package")
                return [pod.metadata.name for pod in pods.items if pod.status.phase == 'Running']
        except ApiException as e:
            raise RuntimeError(f"Error fetching running pods: {e}") from e

    @staticmethod
    def get_pod_metrics(api: client.CustomObjectsApi, namespace: str, pod_name: str) -> Optional[PodMetrics]:
        try:
            with k8s_api_lock:
                metrics = api.get_namespaced_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                    name=pod_name
                )

                cpu_usage = PodResourceParser.parse_cpu(metrics['containers'][0]['usage']['cpu'])  # type: ignore
                memory_usage = PodResourceParser.parse_memory(
                    metrics['containers'][0]['usage']['memory'])  # type: ignore
                return PodMetrics(cpu=cpu_usage, memory=memory_usage)
        except ApiException as e:
            if e.status == 404:
                return None
            else:
                raise RuntimeError(f"Error fetching pod metrics: {e}") from e

    @staticmethod
    def create_pod(api: client.CoreV1Api, namespace: str, pod_name: str, python_version: str,
                   env_vars: List[Environment], logger: Logger, volumes: List[VolumeMap],
                   image: Optional[str], runtime: Optional[RuntimeType], empty_instance: bool):
        if env_vars is None:
            env_vars = []

        env_vars.append(Environment("PYTHONUNBUFFERED", "1"))
        env_vars.append(Environment("PROXY_PREFIX", f"{config.OPENAPI_PREFIX_PATH}/proxy/{pod_name}/"))

        for env_var in ['http_proxy', 'https_proxy', 'no_proxy']:
            if os.environ.get(env_var):
                env_vars.append(Environment(env_var, os.environ[env_var]))

        env_var_list = [{"name": env_var.name, "value": env_var.value} for env_var in env_vars]

        volume_mounts = [
            {"name": "workdir", "mountPath": "/app"},
            {"name": "venv", "mountPath": "/app/venv"}
        ]
        volumes_list = [
            {"name": "workdir", "emptyDir": {}},
            {"name": "venv", "emptyDir": {}}
        ]

        for volume in volumes:
            volume_mounts.append({
                "name": volume.name.lower(),
                "mountPath": volume.path
            })
            volumes_list.append({
                "name": volume.name.lower(),
                "persistentVolumeClaim": {
                    "claimName": volume.pvc_name
                }
            })

        image_to_use = image if image else f"python:{python_version}-slim"
        container = {
            "name": pod_name,
            "image": image_to_use,
            "volumeMounts": volume_mounts,
            "env": env_var_list,
            "imagePullPolicy": "IfNotPresent"
        }

        if runtime != RuntimeType.CONTAINER or empty_instance:
            container["command"] = ["sleep", "infinity"]

        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "labels": {
                    "app": "lotse-package",
                }
            },
            "spec": {
                "containers": [container],
                "volumes": volumes_list
            }
        }

        try:
            with k8s_api_lock:
                api.create_namespaced_pod(namespace=namespace, body=pod_manifest)
            logger.info(f"Pod created successfully in namespace {namespace}")
        except ApiException as e:
            logger.error(f"Error creating pod: {e}")
            raise

    @staticmethod
    def delete_pod(api: client.CoreV1Api, namespace: str, pod_name: str,
                   logger: Optional[Logger] = None):
        try:
            PodPortManager.terminate_port_forward(pod_name)

            with k8s_api_lock:
                api.delete_namespaced_pod(
                    name=pod_name,
                    namespace=namespace,
                    grace_period_seconds=0,
                    body=client.V1DeleteOptions(
                        propagation_policy='Background',
                        grace_period_seconds=0
                    )
                )

            if logger:
                logger.info(f"Pod {pod_name} force deleted successfully")
        except ApiException as e:
            if logger:
                logger.error(f"Error deleting pod: {e}")

    @staticmethod
    def get_pod_logs(api: client.CoreV1Api, namespace: str, pod_name: str) -> str:
        try:
            with k8s_api_lock:
                logs = api.read_namespaced_pod_log(name=pod_name, namespace=namespace)
                return logs
        except Exception:
            return ""
