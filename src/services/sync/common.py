"""Building blocks shared by Git and image sources."""
import logging
import os
import shutil
import stat
import zlib
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException
from sqlalchemy import text

from src.database.database_access import engine
from src.services.sync.versions import version_of

logger = logging.getLogger(__name__)

# first key of the two-key advisory lock, the second one is derived from the source id
_LOCK_CLASS = 7_452
_MAX_ERROR_LENGTH = 2000


class SourceBusyError(Exception):
    """Another check or sync of the same source is running."""


class SyncConfigError(Exception):
    """The content of the source can't be deployed. Retrying won't help until it changes."""


class SyncStatus:
    UNKNOWN = "Unknown"
    NO_TAGS = "NoTags"
    SYNCED = "Synced"
    OUT_OF_SYNC = "OutOfSync"
    ERROR = "Error"


@contextmanager
def source_lock(source_id: str) -> Iterator[bool]:
    """Postgres advisory lock per source: the poller, webhooks and users never sync a source at the same time,
    even with several Lotse replicas."""
    key = zlib.crc32(source_id.encode()) & 0x7FFFFFFF
    with engine.connect() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:a, :b)"), {"a": _LOCK_CLASS, "b": key}).scalar()
        # end the transaction right away, the lock belongs to the session. An open transaction would
        # block schema migrations of other instances while a slow sync runs.
        connection.commit()
        try:
            yield bool(acquired)
        finally:
            if acquired:
                connection.execute(text("SELECT pg_advisory_unlock(:a, :b)"), {"a": _LOCK_CLASS, "b": key})
                connection.commit()


def describe_error(error: Exception) -> str:
    message = str(error.detail) if isinstance(error, HTTPException) else str(error)
    return (message or type(error).__name__)[:_MAX_ERROR_LENGTH]


def is_permanent(error: Exception) -> bool:
    """Errors caused by the content of the source. Retrying the same commit/digest would fail again."""
    return isinstance(error, (SyncConfigError, HTTPException))


def compute_status(last_checked_at: datetime | None, last_error: str | None, latest_tag: str | None,
                   tag_prefix: str, active_version: str | None) -> str:
    if last_checked_at is None:
        return SyncStatus.UNKNOWN
    if last_error:
        return SyncStatus.ERROR
    if not latest_tag:
        return SyncStatus.NO_TAGS
    return SyncStatus.SYNCED if version_of(latest_tag, tag_prefix) == active_version else SyncStatus.OUT_OF_SYNC


def remove_tree(path: Path) -> None:
    def make_writable_and_retry(function, failed_path, _):
        # git marks its object files read-only, which makes deleting them fail on Windows
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    if not path.exists():
        return
    try:
        shutil.rmtree(path, onexc=make_writable_and_retry)
    except OSError as e:
        logger.warning("Could not remove %s: %s", path, e)
