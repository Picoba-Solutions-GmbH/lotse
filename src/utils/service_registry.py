from src.database.repositories.task_repository import TaskRepository
from src.services.activemq_service import ActiveMQService
from src.services.task_manager_service import TaskManagerService
from src.utils import config


def initialize_registry():
    task_manager = TaskRepository()
    k8s_manager_service = TaskManagerService(task_manager=task_manager)

    ActiveMQService(
        host=config.ACTIVEMQ_HOST,
        port=config.ACTIVEMQ_PORT,
        user=config.ACTIVEMQ_USER,
        password=config.ACTIVEMQ_PASSWORD,
        queue_name=config.ACTIVEMQ_QUEUE_NAME,
        k8s_manager_service=k8s_manager_service
    )
