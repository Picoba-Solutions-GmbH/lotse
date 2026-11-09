import logging
import time
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from src.utils.config import DATABASE_URL

logger = logging.getLogger(__name__)

Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=30,
    max_overflow=50,
    pool_timeout=60,
    pool_pre_ping=True,
    pool_recycle=1800
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def import_models():
    # pylint: disable=import-outside-toplevel,unused-import
    from src.database.models import (package_access_entity,  # noqa: F401
                                     package_entity, task_entity, user_entity,
                                     volume_entity)


def init_db(retries=5, delay=2):
    # pylint: disable=import-outside-toplevel
    from src.database.migrator import migrate_database

    import_models()
    for attempt in range(retries):
        try:
            logger.info("Applying database migrations...")
            migrate_database()
            return True
        except OperationalError as e:
            # Only retry connection problems. A lock timeout is logged by the migrator and won't fix itself.
            if "lock timeout" in str(e).lower() or attempt == retries - 1:
                logger.error(f"Failed to initialize database after {retries} attempts: {str(e)}")
                raise
            logger.warning(f"Database connection attempt {attempt + 1} failed, retrying in {delay} seconds...")
            time.sleep(delay)
