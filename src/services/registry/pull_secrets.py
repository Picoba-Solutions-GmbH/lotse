import logging

from src.database.database_access import SessionLocal
from src.database.repositories.registry_repository import RegistryRepository

logger = logging.getLogger(__name__)


def pull_secrets_for(image: str | None) -> list[str]:
    """imagePullSecrets of the registry an image comes from. Never fails a pod start."""
    if not image:
        return []
    db = SessionLocal()
    try:
        return RegistryRepository.pull_secrets_for(db, image)
    except Exception:
        logger.exception("Could not look up the pull secret for %s", image)
        return []
    finally:
        db.close()
