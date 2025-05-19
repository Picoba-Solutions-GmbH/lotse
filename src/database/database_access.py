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


def init_db(retries=5, delay=2):
    for attempt in range(retries):
        try:
            logger.info("Creating database tables...")
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables created successfully")
            return True
        except OperationalError as e:
            if attempt == retries - 1:
                logger.error(f"Failed to initialize database after {retries} attempts: {str(e)}")
                raise
            logger.warning(f"Database connection attempt {attempt + 1} failed, retrying in {delay} seconds...")
            time.sleep(delay)
