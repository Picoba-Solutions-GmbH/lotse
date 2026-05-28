from typing import Optional

from fastapi import APIRouter, Query

from src.utils.log_store import get_log_handler

router = APIRouter(prefix="/logs", tags=["Logs"])

VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@router.get("")
async def get_logs(
    limit: int = Query(50, ge=1, le=500, description="Number of log entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)"),
    from_date: Optional[str] = Query(None, description="ISO 8601 UTC start datetime, e.g. 2024-01-01T00:00:00Z"),
    to_date: Optional[str] = Query(None, description="ISO 8601 UTC end datetime, e.g. 2024-12-31T23:59:59Z"),
    search: Optional[str] = Query(None, description="Case-insensitive substring search in message/logger"),
):
    records = get_log_handler().get_records()

    if level:
        level_upper = level.upper()
        records = [r for r in records if r["level"] == level_upper]

    if from_date:
        records = [r for r in records if r["timestamp"] >= from_date]

    if to_date:
        records = [r for r in records if r["timestamp"] <= to_date]

    if search:
        needle = search.lower()
        records = [
            r for r in records
            if needle in r["message"].lower() or needle in r["logger"].lower()
        ]

    total = len(records)
    page = records[offset: offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": page,
    }
