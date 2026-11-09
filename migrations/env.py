# pylint: disable=no-member,unused-argument  # alembic.context is populated at runtime
import logging
from datetime import datetime, timezone
from logging.config import fileConfig

from alembic import context
from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table,
                        engine_from_config, pool)

from src.database.database_access import Base, import_models
from src.utils import config as app_config

alembic_config = context.config

# Only configure logging when run from the alembic CLI, the app has its own logging setup.
if alembic_config.config_file_name is not None and alembic_config.attributes.get("configure_logger", True):
    fileConfig(alembic_config.config_file_name, disable_existing_loggers=False)

logger = logging.getLogger("alembic.env")

import_models()
target_metadata = Base.metadata

# Like __EFMigrationsHistory: one row per applied migration step.
# alembic_version only stores the current revision, this table keeps the full history.
history_metadata = MetaData()
migration_history = Table(
    "migration_history",
    history_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("revision", String(64), nullable=False),
    Column("description", String, nullable=True),
    Column("operation", String(16), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


def _include_object(obj, name, type_, reflected, compare_to):
    # The history table is maintained by this file, not by the models.
    return not (type_ == "table" and name == migration_history.name)


def _record_history(ctx, step, heads, run_args):
    if step.is_stamp:
        operation = "stamp"
    elif step.is_upgrade:
        operation = "upgrade"
    else:
        operation = "downgrade"

    revision_id = step.up_revision_id
    script = step.up_revision
    description = script.doc if script is not None else None

    ctx.connection.execute(migration_history.insert().values(
        revision=revision_id,
        description=description,
        operation=operation,
        applied_at=datetime.now(timezone.utc),
    ))
    logger.info("%s %s (%s)", operation, revision_id, description)


def _database_url() -> str:
    return context.get_x_argument(as_dictionary=True).get("url") or app_config.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    history_metadata.create_all(connection)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        on_version_apply=_record_history,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    # SQLAlchemy 2.0 autobegins a transaction (create_all above), so commit explicitly.
    connection.commit()


def run_migrations_online() -> None:
    # The application passes its own connection (see src/database/migrator.py).
    connection = alembic_config.attributes.get("connection")
    if connection is not None:
        _run_migrations(connection)
        return

    engine = engine_from_config({"sqlalchemy.url": _database_url()}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
