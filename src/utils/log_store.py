import logging
import threading
from collections import deque
from datetime import datetime, timezone

_ACCESS_LOGGERS = {"uvicorn.access", "uvicorn.error", "starlette.access"}


class InMemoryLogHandler(logging.Handler):
    def __init__(self, maxlen: int):
        super().__init__()
        self._lock = threading.Lock()
        self._records: deque[dict] = deque(maxlen=maxlen)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        if record.name in _ACCESS_LOGGERS or getattr(record, "msgType", None) == "Request":
            return

        try:
            msg = self.format(record)
            if record.exc_info:
                record.exc_text = None

            entry = {
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            }
            with self._lock:
                self._records.append(entry)
        except Exception:
            self.handleError(record)

    def get_records(self) -> list[dict]:
        with self._lock:
            return list(self._records)


_handler: InMemoryLogHandler | None = None


def setup_log_handler(maxlen: int = 5000) -> None:
    global _handler  # pylint: disable=global-statement
    _handler = InMemoryLogHandler(maxlen=maxlen)
    logging.getLogger().addHandler(_handler)


def get_log_handler() -> InMemoryLogHandler:
    if _handler is None:
        raise RuntimeError("Log handler not initialised – call setup_log_handler() first.")
    return _handler
