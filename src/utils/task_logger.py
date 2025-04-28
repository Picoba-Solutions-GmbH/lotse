import logging
import os
import platform
from pathlib import Path
from typing import List

from src.utils import config


class TaskLogger:
    def __init__(self):
        self.logs_dir = self._get_system_logs_path()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.loggers = {}

    def _get_system_logs_path(self) -> Path:
        system = platform.system().lower()

        if system == "windows":
            base_path = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'))
            return base_path / config.company_dir / config.app_name / "logs"
        elif system == "linux":
            return Path("/var") / config.company_dir / config.app_name / "logs"

        return Path.home() / config.company_dir / config.app_name / "logs"

    def get_log_file_path(self, task_id: str) -> Path:
        task_logs_dir = self.logs_dir / task_id
        task_logs_dir.mkdir(exist_ok=True)
        return task_logs_dir / "task.log"

    def setup_logger(self, task_id: str) -> logging.Logger:
        if task_id in self.loggers:
            return self.loggers[task_id]

        logger = logging.getLogger(f"task.{task_id}")
        logger.setLevel(logging.INFO)
        logger.handlers = []
        logger.propagate = False

        log_file = self.get_log_file_path(task_id)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        logger.addHandler(file_handler)
        self.loggers[task_id] = logger
        return logger

    def get_logs(self, task_id: str) -> List[str]:
        log_file = self.get_log_file_path(task_id)
        if not log_file.exists():
            return []

        with open(log_file, 'r', encoding="utf-8") as f:
            lines = f.readlines()
            return lines

    def clear_logs(self, task_id: str) -> bool:
        try:
            log_file = self.get_log_file_path(task_id)
            if log_file.exists():
                os.remove(log_file)

            if task_id in self.loggers:
                del self.loggers[task_id]

            return True
        except Exception:
            return False
