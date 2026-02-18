import importlib

from src.abstractions.message_parser import (JsonMessageParser,
                                             MessageParserProtocol)
from src.database.repositories.task_repository import TaskRepository
from src.services.activemq_service import ActiveMQService
from src.services.task_manager_service import TaskManagerService
from src.utils import config


def _get_message_parser() -> MessageParserProtocol:
    if config.MESSAGE_PARSER_CLASS:
        module_path, class_name = config.MESSAGE_PARSER_CLASS.rsplit(".", 1)
        module = importlib.import_module(module_path)
        parser_class = getattr(module, class_name)
        return parser_class()

    return JsonMessageParser()


def initialize_registry():
    task_manager = TaskRepository()
    k8s_manager_service = TaskManagerService(task_manager=task_manager)

    ActiveMQService(
        host=config.ACTIVEMQ_HOST,
        port=config.ACTIVEMQ_PORT,
        user=config.ACTIVEMQ_USER,
        password=config.ACTIVEMQ_PASSWORD,
        queue_name=config.ACTIVEMQ_QUEUE_NAME,
        k8s_manager_service=k8s_manager_service,
        message_parser=_get_message_parser()
    )
