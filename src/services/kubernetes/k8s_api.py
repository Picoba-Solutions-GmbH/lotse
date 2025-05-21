import asyncio
import os
import re
import subprocess
import threading
from logging import Logger
from typing import Any, Optional

from kubernetes import client
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

from src.misc.runtime_type import RuntimeType
from src.misc.task_status import TaskStatus
from src.models.k8s.volume_map import VolumeMap
from src.models.sync_execution_response import SyncExecutionResponse
from src.models.yaml_config import Environment
from src.services.task_manager_service import TaskManagerService
from src.utils import config, global_queue_handler

k8s_api_lock = threading.Lock()

port_forwards = {}


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


def get_running_pods(api: client.CoreV1Api, namespace: str) -> list[str]:
    try:
        with k8s_api_lock:
            pods = api.list_namespaced_pod(namespace=namespace, label_selector="app=lotse-package")
            return [pod.metadata.name for pod in pods.items if pod.status.phase == 'Running']
    except ApiException as e:
        raise RuntimeError(f"Error fetching running pods: {e}") from e


def get_pod_metrics(api: client.CustomObjectsApi, namespace: str, pod_name: str):
    try:
        with k8s_api_lock:
            metrics = api.get_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
                name=pod_name
            )
            return metrics
    except ApiException as e:
        if e.status == 404:
            return None
        else:
            raise RuntimeError(f"Error fetching pod metrics: {e}") from e


def create_pod(api: client.CoreV1Api, namespace: str, pod_name: str, python_version: str,
               env_vars: list[Environment], task_logger: Logger, volumes: list[VolumeMap],
               image: Optional[str], runtime: Optional[RuntimeType], empty_instance: bool):
    if env_vars is None:
        env_vars = []

    env_vars.append(Environment("PYTHONUNBUFFERED", "1"))
    env_vars.append(Environment("PROXY_PREFIX", f"{config.OPENAPI_PREFIX_PATH}/proxy/{pod_name}/"))

    if os.environ.get('http_proxy'):
        env_vars.append(Environment("http_proxy", os.environ['http_proxy']))
    if os.environ.get('https_proxy'):
        env_vars.append(Environment("https_proxy", os.environ['https_proxy']))
    if os.environ.get('no_proxy'):
        env_vars.append(Environment("no_proxy", os.environ['no_proxy']))

    env_var_list = [{"name": env_var.name, "value": env_var.value} for env_var in env_vars]

    volume_mounts = [
        {
            "name": "workdir",
            "mountPath": "/app"
        },
        {
            "name": "venv",
            "mountPath": "/app/venv"
        }
    ]
    volumes_list = [
        {
            "name": "workdir",
            "emptyDir": {}
        },
        {
            "name": "venv",
            "emptyDir": {}
        }
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

        task_logger.info(f"Pod created successfully in namespace {namespace}")
    except ApiException as e:
        task_logger.error(f"Error creating pod: {e}")
        raise


async def wait_for_pod_running(api: client.CoreV1Api, namespace: str, pod_name: str,
                               task_logger: Logger):
    while True:
        with k8s_api_lock:
            pod = api.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.status.phase == 'Running':  # type: ignore
                return True

            task_logger.info(f"Waiting for pod to be running... Current status: {pod.status.phase}")  # type: ignore
        await asyncio.sleep(1)


async def check_container_exists(api: client.CoreV1Api, namespace: str, pod_name: str) -> bool:
    try:
        with k8s_api_lock:
            pod = api.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.status.container_statuses:  # type: ignore
                all_ready = all(container.ready for container in pod.status.container_statuses)  # type: ignore
                return all_ready

            return False
    except ApiException as e:
        if e.status == 404:  # Pod not found
            return False

        if e.status == 0:
            return True

        return False
    except Exception:
        return False


def get_pod_logs(api: client.CoreV1Api, namespace: str, pod_name: str) -> str:
    try:
        with k8s_api_lock:
            logs = api.read_namespaced_pod_log(name=pod_name, namespace=namespace)
            return logs
    except Exception:
        return ""


def copy_files_to_pod(namespace: str, pod_name: str, file_to_copy, dest_path="/app"):
    is_directory = os.path.isdir(file_to_copy)

    source_dir = os.path.dirname(file_to_copy) if not is_directory else file_to_copy
    file_name = os.path.basename(file_to_copy) if not is_directory else '.'

    kubectl_command = [
        'kubectl', 'cp',
        file_name,
        f"{namespace}/{pod_name}:{dest_path}",

    ]
    subprocess.run(kubectl_command, check=True, cwd=source_dir)


def delete_pod(api: client.CoreV1Api, namespace: str, pod_name: str,
               task_logger: Optional[Logger] = None):
    try:
        terminate_port_forward(pod_name)

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

        if task_logger:
            task_logger.info(f"Pod {pod_name} force deleted successfully")
    except ApiException as e:
        if task_logger:
            task_logger.error(f"Error deleting pod: {e}")


def setup_venv(api: client.CoreV1Api, namespace: str, pod_name: str,
               requirements_path: str, task_logger: Logger):
    shell_to_use = get_available_shell(api, namespace, pod_name)
    exec_command = [
        shell_to_use, '-c',
        f'python -m venv /app/venv && . /app/venv/bin/activate && '
        f'pip install -r {requirements_path}; echo "EXIT_CODE=$?"'
    ]

    with k8s_api_lock:
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False
        )

    exit_code = None
    try:
        while resp.is_open():
            if resp.peek_stdout():
                line = resp.read_stdout()
                task_logger.info(line)
                exit_code_match = re.search(r'EXIT_CODE=(\d+)', line)
                if exit_code_match:
                    exit_code = int(exit_code_match.group(1))
                    continue

            if resp.peek_stderr():
                task_logger.info(resp.read_stderr())
    finally:
        resp.close()

    if exit_code is not None and exit_code != 0:
        message = f"Virtual environment setup failed with exit code {exit_code}"
        task_logger.error(message)
        raise RuntimeError(message)

    task_logger.info("Virtual environment created successfully")


def copy_file_from_pod(api: client.CoreV1Api, namespace: str, pod_name: str,
                       src_path: str, dest_path: str, task_logger: Logger):
    tar_command = ['tar', 'czf', '/tmp/venv.tar.gz', '-C', src_path, '.']

    with k8s_api_lock:
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=tar_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False
        )

    while resp.is_open():
        if resp.peek_stdout():
            task_logger.info(resp.read_stdout())
        if resp.peek_stderr():
            task_logger.info(resp.read_stderr())

    resp.close()

    is_directory = os.path.isdir(dest_path)
    directory_path = os.path.dirname(dest_path) if not is_directory else dest_path
    file_name = os.path.basename(dest_path) if not is_directory else '.'

    kubectl_command = [
        'kubectl', 'cp',
        f"{namespace}/{pod_name}:/tmp/venv.tar.gz",
        file_name
    ]
    subprocess.run(kubectl_command, check=True, cwd=directory_path)


def extract_tar_gz(api: client.CoreV1Api, namespace: str, pod_name:
                   str, src_path: str, dest_path: str, task_logger: Logger):
    tar_command = ['tar', 'xzf', src_path, '-C', dest_path]

    with k8s_api_lock:
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=tar_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False
        )

    while resp.is_open():
        if resp.peek_stdout():
            task_logger.info(resp.read_stdout())
        if resp.peek_stderr():
            task_logger.info(resp.read_stderr())

    resp.close()


async def match_port(pod_name: str,
                     line: str,
                     api: client.CoreV1Api,
                     namespace: str,
                     task_logger: Logger,
                     task_id: str,
                     task_manager: TaskManagerService) -> bool:
    try:
        match = re.search(
            r'((?:\d{1,3}\.){3}\d{1,3}|(?:\[?[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4}){7}\]?)):(\d+)', line)
        if match:
            url = match.group(1)
            port = match.group(2)
            pod = api.read_namespaced_pod(name=pod_name, namespace=namespace)
            task_logger.info(f"Detected URL: {url}, Port: {port}")
            task_manager.update_task_ui_info(
                task_id, True, pod.status.pod_ip, int(port))  # type: ignore

            if config.IS_DEBUG:
                await port_forward_for_debug(namespace, pod_name, task_logger,
                                             task_id, task_manager, int(port))
            return True
    except Exception:
        pass

    return False


async def watch_pod(api: client.CoreV1Api, namespace: str, pod_name: str,
                    task_logger: Logger, task_id: str, task_manager: TaskManagerService) -> Optional[int]:
    port_matched = False
    while True:
        container_exists = await check_container_exists(api, namespace, pod_name)
        if container_exists:
            if not port_matched:
                logs = get_pod_logs(api, namespace, pod_name)
                port_matched = await match_port(
                    pod_name, logs, api, namespace, task_logger, task_id, task_manager)

            await asyncio.sleep(0.1)
        else:
            delete_pod(api, namespace, pod_name, task_logger)
            return 0


def start_app(api: client.CoreV1Api, namespace: str, pod_name: str, entry_point: str,
              args: list[str], task_logger: Logger, task_id: str, task_manager: TaskManagerService,
              runtime: Optional[RuntimeType] = RuntimeType.PYTHON) -> Optional[int]:
    pre_start_command = None
    match runtime:
        case RuntimeType.PYTHON:
            pre_start_command = f". venv/bin/activate && python -u {entry_point}"
        case RuntimeType.BINARY:
            pre_start_command = f"chmod +x {entry_point} && ./{entry_point}"

    shell_to_use = get_available_shell(api, namespace, pod_name)
    exec_command = [shell_to_use, '-c',
                    f'cd /app && {pre_start_command} {" ".join(args)}; echo "EXIT_CODE=$?"']

    with k8s_api_lock:
        resp = stream(api.connect_get_namespaced_pod_exec,
                      pod_name,
                      namespace,
                      command=exec_command,
                      stderr=True,
                      stdin=True,
                      stdout=True,
                      tty=False,
                      _preload_content=False)

    port_matched = False
    exit_code = None
    kill_command_received = False
    try:
        while resp.is_open():
            line: Optional[str] = None
            if resp.peek_stdout():
                line = resp.read_stdout()

            if resp.peek_stderr():
                line = resp.read_stderr()

            if line is None:
                continue

            task_logger.info(line.strip())
            exit_code_match = re.search(r'EXIT_CODE=(\d+)', line)
            if exit_code_match:
                exit_code = int(exit_code_match.group(1))
                continue

            if not port_matched:
                port_matched = asyncio.run(match_port(
                    pod_name, line, api, namespace, task_logger, task_id, task_manager))
    finally:
        resp.close()

        task = task_manager.get_task(task_id)
        if task is not None and (task.status == TaskStatus.CANCELLED or kill_command_received):
            exit_code = 0
        else:
            delete_pod(api, namespace, pod_name, task_logger)

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


async def port_forward_for_debug(namespace, pod_name, task_logger: Logger,
                                 task_id: str, task_manager, port: int):
    if config.IS_DEBUG:
        result = await port_forward(namespace, pod_name, port)
        if result:
            _, local_port = result
            if local_port:
                task_logger.info(
                    f"Port forwarding active: localhost:{local_port} -> {pod_name}:{port}")
                task_manager.update_task_ui_info(
                    task_id, True, "localhost", int(local_port))


async def port_forward(namespace, pod_name, remote_port):
    cmd = ["kubectl", "port-forward", f"pod/{pod_name}", f":{remote_port}", "-n", namespace]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    port_pattern = re.compile(r"Forwarding from 127.0.0.1:(\d+)")
    local_port = None

    for _ in range(10):
        try:
            line = await asyncio.wait_for(process.stdout.readline(), 0.5)  # type: ignore
            if not line:
                break

            line_text = line.decode('utf-8')
            match = port_pattern.search(line_text)
            if match:
                local_port = int(match.group(1))
                break
        except asyncio.TimeoutError:
            if process.returncode is not None:
                break

    if local_port:
        print(f"Port forwarding active: localhost:{local_port} -> {pod_name}:{remote_port}")
        port_forwards[pod_name] = process
        return process, local_port
    else:
        print("Failed to establish port forwarding or detect port")
        if process.returncode is None:
            process.terminate()
        return None, None


def terminate_port_forward(pod_name):
    if config.IS_DEBUG:
        if pod_name in port_forwards:
            process = port_forwards[pod_name]
            if process:
                process.terminate()
                del port_forwards[pod_name]


def install_ssh_server(api: client.CoreV1Api, namespace: str, pod_name: str,
                       username: str, password: str, task_logger: Logger):
    exec_command = [
        'bash', '-c',
        f'''
        apt-get update && apt-get install -y openssh-server sudo
        mkdir -p /run/sshd
        service ssh start
        sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
        adduser --disabled-password --gecos "" {username}
        echo "{username}:{password}" | chpasswd
        usermod -aG sudo {username}
        service ssh restart
        echo "SSH server installed and configured. User {username} created with password {password}"
        '''
    ]
    with k8s_api_lock:
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False
        )
    while resp.is_open():
        if resp.peek_stdout():
            task_logger.info(resp.read_stdout())
        if resp.peek_stderr():
            task_logger.info(resp.read_stderr())
    resp.close()
    task_logger.info(f"SSH server installed in pod {pod_name}")


def install_and_run_vscode_server(api: client.CoreV1Api, namespace: str, pod_name: str,
                                  task_logger: Logger, task_manager: TaskManagerService):
    exec_command = [
        'bash', '-c',
        '''
        # Install necessary packages if not already installed
        apt-get update && apt-get install -y curl jq procps

        if ! command -v code-server &> /dev/null; then
            echo "Installing code-server..."
            curl -fsSL https://code-server.dev/install.sh | sh
            jq '. += {"extensionsGallery": {
                "serviceUrl": "https://marketplace.visualstudio.com/_apis/public/gallery",
                "itemUrl": "https://marketplace.visualstudio.com/items"
            }}' /usr/lib/code-server/lib/vscode/product.json > temp.json
            mv temp.json /usr/lib/code-server/lib/vscode/product.json
            code-server --install-extension ms-python.python
            echo "Extension installation completed"
        else
            echo "code-server is already installed"
        fi

        code-server --disable-telemetry --auth=none --bind-addr=0.0.0.0:8080
        '''
    ]

    with k8s_api_lock:
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False
        )

    while resp.is_open():
        if resp.peek_stdout():
            line = resp.read_stdout()
            task_logger.info(line)
            if "server listening" in line:
                resp.close()
        if resp.peek_stderr():
            task_logger.info(resp.read_stderr())

    resp.close()

    vs_code_port = 8080
    if config.IS_DEBUG:
        async def port_forward_vscode():
            result = await port_forward(namespace, pod_name, vs_code_port)
            if result:
                _, local_port = result
                if local_port:
                    task_manager.update_vscode_port(pod_name, int(local_port))
        task_queue = global_queue_handler.GlobalQueueHandlerSingleton.get_instance()
        task_queue.enqueue(port_forward_vscode)
    else:
        task_manager.update_vscode_port(pod_name, vs_code_port)

    task_logger.info(f"VSCode server installed and running in pod {pod_name}")


def run_command_in_pod(api: client.CoreV1Api, namespace: str, pod_name: str,
                       command: list[str], task_logger: Logger):
    with k8s_api_lock:
        resp = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False
        )

    while resp.is_open():
        if resp.peek_stdout():
            task_logger.info(resp.read_stdout())
        if resp.peek_stderr():
            task_logger.info(resp.read_stderr())

    resp.close()


def get_available_shell(api: client.CoreV1Api, namespace: str, pod_name: str) -> str:
    shells = ["/bin/bash", "/bin/sh"]
    for shell in shells:
        try:
            with k8s_api_lock:
                check_resp = stream(
                    api.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    command=["ls", shell],
                    stderr=True,
                    stdout=True,
                    _preload_content=False
                )
                check_resp.run_forever(timeout=2)
                if check_resp.returncode == 0:
                    return shell
        except Exception:
            continue

    return "/bin/sh"
