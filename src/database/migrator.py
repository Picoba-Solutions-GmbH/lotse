import logging
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from src.database.database_access import engine

logger = logging.getLogger(__name__)

# The first migration. It describes the schema as it was created by Base.metadata.create_all
# before migrations were introduced.
BASELINE_REVISION = "0001_initial"

# Arbitrary but fixed key so that only one lotse instance migrates at a time.
_MIGRATION_LOCK_KEY = 7_451_993_001

# Schema changes need exclusive table locks. Instead of waiting forever for another session
# (e.g. a leaked "idle in transaction" connection of another lotse instance), fail with a clear error.
_LOCK_TIMEOUT = "30s"

_ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")


def _alembic_config(connection) -> Config:
    config = Config(os.path.abspath(_ALEMBIC_INI))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


def migrate_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK_KEY})
        connection.execute(text(f"SET lock_timeout = '{_LOCK_TIMEOUT}'"))
        try:
            config = _alembic_config(connection)
            tables = inspect(connection).get_table_names()

            if "alembic_version" not in tables and "Packages" in tables:
                # Database was created before migrations existed: its schema matches the baseline.
                logger.info("Existing database without migration history, marking %s as applied", BASELINE_REVISION)
                command.stamp(config, BASELINE_REVISION)

            command.upgrade(config, "head")
            logger.info("Database is up to date")
        except OperationalError as e:
            if "lock timeout" in str(e).lower():
                connection.rollback()
                _log_blocking_sessions(connection)
            raise
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK_KEY})
            connection.commit()


def _log_blocking_sessions(connection) -> None:
    rows = connection.execute(text("""
        SELECT a.pid, a.client_addr, a.state, now() - a.xact_start AS transaction_age, left(a.query, 120) AS query
        FROM pg_locks l
        JOIN pg_stat_activity a ON a.pid = l.pid
        JOIN pg_class c ON c.oid = l.relation
        WHERE a.pid <> pg_backend_pid() AND a.datname = current_database() AND c.relnamespace = 'public'::regnamespace
        GROUP BY a.pid, a.client_addr, a.state, a.xact_start, a.query
    """)).all()
    logger.error(
        "Database migration timed out waiting for a table lock. Sessions holding locks: %s. "
        "Close these sessions (e.g. restart the other lotse instance or SELECT pg_terminate_backend(<pid>)).",
        [dict(row._mapping) for row in rows])
