from src.services.activemq_service import ActiveMQService
from src.services.kubernetes.k8s_manager_service import K8sManagerService
from src.services.task_manager_service import TaskManagerService
from src.utils import config


def initialize_registry():
    task_manager = TaskManagerService()
    k8s_manager_service = K8sManagerService(task_manager=task_manager)

    ActiveMQService(
        host=config.ACTIVEMQ_HOST,
        port=config.ACTIVEMQ_PORT,
        user=config.ACTIVEMQ_USER,
        password=config.ACTIVEMQ_PASSWORD,
        queue_name=config.ACTIVEMQ_QUEUE_NAME,
        k8s_manager_service=k8s_manager_service
    )
