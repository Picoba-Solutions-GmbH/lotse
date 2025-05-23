import threading
from logging import Logger

from kubernetes import client

from .pod_executor import PodExecutor

k8s_api_lock = threading.Lock()


class PodEnvironment:
    @staticmethod
    def install_ssh_server(api: client.CoreV1Api, namespace: str, pod_name: str,
                           username: str, password: str, logger: Logger):
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

        def line_callback(line: str) -> bool:
            logger.info(line)
            return False

        PodExecutor.run_command(api, namespace, pod_name, exec_command, line_callback)
        logger.info(f"SSH server installed in pod {pod_name}")

    @staticmethod
    def install_and_run_vscode_server(api: client.CoreV1Api, namespace: str, pod_name: str,
                                      logger: Logger):
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

        def line_callback(line: str) -> bool:
            logger.info(line)
            if "server listening" in line:
                return True

            return False

        PodExecutor.run_command(api, namespace, pod_name, exec_command, line_callback)
        logger.info(f"VSCode server installed and running in pod {pod_name}")
