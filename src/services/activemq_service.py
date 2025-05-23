import logging
import threading

import stomp

from src.services.package_execution_listener_service import \
    PackageExecutionListenerService
from src.services.task_manager_service import TaskManagerService
from src.utils.singleton_meta import SingletonMeta

logger = logging.getLogger(__name__)


class ActiveMQService(metaclass=SingletonMeta):
    def __init__(self, host: str, port: int, user: str,
                 password: str, queue_name: str, k8s_manager_service: TaskManagerService):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.queue_name = queue_name
        self.k8s_manager_service = k8s_manager_service

    def setup_connection(self):
        conn = stomp.Connection([(self.host, self.port)])
        conn.set_listener('', PackageExecutionListenerService(self.k8s_manager_service))
        conn.connect(self.user, self.password, wait=True)
        conn.subscribe(destination=self.queue_name, id=1, ack='auto')
        return conn

    def start_listener(self):
        try:
            conn = self.setup_connection()
            logger.info("Connected to ActiveMQ")
            while True:
                if not conn.is_connected():
                    logger.warning("ActiveMQ connection lost, reconnecting...")
                    conn = self.setup_connection()
                threading.Event().wait(100)
        except Exception as e:
            logger.error(f"ActiveMQ connection error: {str(e)}")
