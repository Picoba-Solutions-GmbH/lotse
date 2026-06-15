import logging
import time

import stomp

from src.abstractions.message_parser import MessageParserProtocol
from src.services.package_execution_listener_service import \
    PackageExecutionListenerService
from src.services.task_manager_service import TaskManagerService
from src.utils.singleton_meta import SingletonMeta

logger = logging.getLogger(__name__)

_RECONNECT_INTERVAL = 5
_POLL_INTERVAL = 5
_HEARTBEAT_MS = 10_000


class ActiveMQService(metaclass=SingletonMeta):
    def __init__(self, host: str, port: int, user: str,
                 password: str, queue_name: str, k8s_manager_service: TaskManagerService,
                 message_parser: MessageParserProtocol):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.queue_name = queue_name
        self.k8s_manager_service = k8s_manager_service
        self.message_parser = message_parser
        self._connected: bool = False

    def setup_connection(self):
        conn = stomp.Connection([(self.host, self.port)], heartbeats=(_HEARTBEAT_MS, _HEARTBEAT_MS), keepalive=True)
        conn.set_listener('', PackageExecutionListenerService(self.k8s_manager_service, self.message_parser))
        conn.connect(self.user, self.password, wait=True)
        conn.subscribe(destination=self.queue_name, id=1, ack='auto')
        return conn

    def _try_connect(self) -> "stomp.Connection | None":
        try:
            conn = self.setup_connection()
            self._connected = True
            logger.info("Connected to ActiveMQ")
            return conn
        except Exception as e:
            self._connected = False
            logger.error(f"ActiveMQ connection failed: {e}")
            return None

    def start_listener(self):
        conn = None

        while True:
            if conn is None or not conn.is_connected():
                if conn is not None:
                    self._connected = False
                    logger.warning("ActiveMQ connection lost, reconnecting in %ds…", _RECONNECT_INTERVAL)
                    try:
                        conn.disconnect()
                    except Exception:
                        pass
                    time.sleep(_RECONNECT_INTERVAL)

                conn = self._try_connect()
                if conn is None:
                    time.sleep(_RECONNECT_INTERVAL)
                    continue

            time.sleep(_POLL_INTERVAL)

    @property
    def is_connected(self) -> bool:
        return self._connected
