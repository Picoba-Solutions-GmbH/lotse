"""One background loop for all sources: Git sources, image sources and registry discovery."""
import logging
import threading
import time
from pathlib import Path

from src.services.git_sync_service import GitSyncReconciler
from src.services.image_sync_service import ImageSyncReconciler
from src.services.sync.common import remove_tree
from src.utils import config

logger = logging.getLogger(__name__)


class SourceReconciler:
    _lock = threading.Lock()
    _started = False

    @classmethod
    def start(cls) -> None:
        with cls._lock:
            if cls._started:
                return
            cls._started = True
        remove_tree(Path(config.GIT_WORK_ROOT))  # leftovers of a crash
        threading.Thread(target=cls._loop, daemon=True, name="source-sync").start()
        logger.info("Source sync started, looking for due sources every %s s", config.GIT_SYNC_TICK_SECONDS)

    @classmethod
    def _loop(cls) -> None:
        while True:
            cls.run_once()
            time.sleep(config.GIT_SYNC_TICK_SECONDS)

    @staticmethod
    def run_once() -> None:
        for reconciler in (GitSyncReconciler, ImageSyncReconciler):
            try:
                reconciler.run_once()
            except Exception:
                logger.exception("%s iteration failed", reconciler.__name__)
