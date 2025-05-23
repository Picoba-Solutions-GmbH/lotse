import asyncio
import re
import threading
from logging import Logger
from typing import Dict, Optional, Tuple

from src.database.repositories.task_repository import TaskRepository

k8s_api_lock = threading.Lock()
port_forwards: Dict[str, asyncio.subprocess.Process] = {}  # pylint: disable=E1101


class PodPortManager:
    @staticmethod
    def terminate_port_forward(pod_name: str):
        if pod_name in port_forwards:
            process = port_forwards[pod_name]
            if process:
                process.terminate()
                del port_forwards[pod_name]

    @staticmethod
    async def port_forward(
        namespace: str,
        pod_name: str,
        remote_port: int
    ) -> Optional[Tuple[asyncio.subprocess.Process, int]]:  # pylint: disable=E1101
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
            return None

    @staticmethod
    async def port_forward_local(namespace: str, pod_name: str, logger: Logger,
                                 task_id: str, task_manager: TaskRepository, port: int):
        result = await PodPortManager.port_forward(namespace, pod_name, port)
        if result:
            _, local_port = result
            if local_port:
                logger.info(
                    f"Port forwarding active: localhost:{local_port} -> {pod_name}:{port}")
                task_manager.update_task_ui_info(
                    task_id, True, "localhost", int(local_port))
