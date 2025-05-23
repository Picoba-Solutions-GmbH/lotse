import threading
from typing import Callable, List, Optional

from kubernetes import client
from kubernetes.stream import stream

k8s_api_lock = threading.Lock()


class PodExecutor:
    @staticmethod
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

    @staticmethod
    def run_command(api: client.CoreV1Api, namespace: str, pod_name: str,
                    command: List[str], callback: Optional[Callable[[str], bool]] = None) -> Optional[int]:
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

        exit_code = None
        try:
            while resp.is_open():
                line = None
                if resp.peek_stdout():
                    line = resp.read_stdout()

                if resp.peek_stderr():
                    line = resp.read_stderr()

                if line:
                    line = line.strip()
                    if line is None:
                        continue

                    if callback:
                        close_response = callback(line)
                        if close_response:
                            resp.close()
                            return 0

            resp.update(timeout=1)
            exit_code = resp.returncode
        finally:
            resp.close()

        return exit_code
