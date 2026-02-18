import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import stomp

from src.abstractions.message_parser import MessageParserProtocol
from src.services.task_manager_service import TaskManagerService

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def get_event_loop():
    if not hasattr(_thread_local, "loop"):
        _thread_local.loop = asyncio.new_event_loop()
    return _thread_local.loop


class PackageExecutionListenerService(stomp.ConnectionListener):
    def __init__(self, k8s_manager_service: TaskManagerService, message_parser: MessageParserProtocol, max_workers=10):
        self.k8s_manager_service = k8s_manager_service
        self.message_parser = message_parser
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def on_message(self, frame):
        try:
            request = self.message_parser.parse_message(frame.body)
            logger.info(f"Received message for script: {request.package_name}")
            self.executor.submit(self._run_task, request.package_name,
                                 request.version, request.arguments)
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)

    def _run_task(self, package_name: str, version: str | None, arguments: list):
        loop = get_event_loop()
        try:
            loop.run_until_complete(self._process_message(package_name, version, arguments))
        except Exception as e:
            logger.error(f"Error in async task execution: {str(e)}", exc_info=True)

    async def _process_message(self, package_name: str, version: str | None, arguments: list):
        try:
            await self.k8s_manager_service.execute_package_async(package_name, version, arguments, False)
        except Exception as e:
            logger.error(f"Error executing script: {str(e)}", exc_info=True)

    def shutdown(self):
        self.executor.shutdown(wait=True)
        for thread in threading.enumerate():
            if hasattr(thread, "loop"):
                thread.loop.close()  # type: ignore
