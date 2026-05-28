from fastapi import APIRouter

from src.utils import config

router = APIRouter(tags=["Status"])


@router.get("/health", include_in_schema=False)
def health_check():
    return {"status": "UP"}


@router.get("/liveness", include_in_schema=False)
def liveness_check():
    return {"status": "UP"}


@router.get("/status")
def get_status():
    result: dict = {
        "server": "UP",
        "activemq_enabled": config.ACTIVEMQ_ACTIVE,
    }

    if config.ACTIVEMQ_ACTIVE:
        try:
            from src.services.activemq_service import ActiveMQService
            from src.utils.singleton_meta import get_service_instance
            amq: ActiveMQService = get_service_instance(ActiveMQService)
            result["activemq_connected"] = amq.is_connected
        except Exception:
            result["activemq_connected"] = False

    return result
