import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import stomp

from src.models.execution_request import ExecutionRequest
from src.services.kubernetes.k8s_manager_service import K8sManagerService

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def get_event_loop():
    if not hasattr(_thread_local, "loop"):
        _thread_local.loop = asyncio.new_event_loop()
    return _thread_local.loop


class PackageExecutionListenerService(stomp.ConnectionListener):
    def __init__(self, k8s_manager_service: K8sManagerService, max_workers=10):
        self.k8s_manager_service = k8s_manager_service
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def on_message(self, frame):
        try:
            message = json.loads(frame.body)
            request = ExecutionRequest(**message)
            logger.info(f"Received message for script: {request.package_name}")
            self.executor.submit(self._run_task, request.package_name, request.stage,
                                 request.version, request.arguments)
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)

    def _run_task(self, package_name: str, stage: str, version: Optional[str], arguments: list):
        loop = get_event_loop()
        try:
            loop.run_until_complete(self._process_message(package_name, stage, version, arguments))
        except Exception as e:
            logger.error(f"Error in async task execution: {str(e)}", exc_info=True)

    async def _process_message(self, package_name: str, stage: str, version: Optional[str], arguments: list):
        try:
            await self.k8s_manager_service.execute_package_async(package_name, stage, version, arguments)
        except Exception as e:
            logger.error(f"Error executing script: {str(e)}", exc_info=True)

    def shutdown(self):
        self.executor.shutdown(wait=True)
        for thread in threading.enumerate():
            if hasattr(thread, "loop"):
                thread.loop.close()  # type: ignore
