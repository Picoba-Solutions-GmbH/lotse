import logging
import os
import platform
from pathlib import Path

from src.utils import config

logger = logging.getLogger(__name__)


class VenvManager:
    def __init__(self):
        self.base_venv_path = self._get_base_venv_path()
        self.base_venv_path.mkdir(parents=True, exist_ok=True)

    def _get_base_venv_path(self) -> Path:
        system = platform.system().lower()

        if system == "windows":
            base_path = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'))
            return base_path / config.company_dir / config.app_name / "venvs"
        elif system == "linux":
            return Path("/var") / config.company_dir / config.app_name / "venvs"

        return Path.home() / config.company_dir / config.app_name / "venvs"

    def get_venv_path(self, package_name: str, version: str, stage: str) -> Path:
        versioned_path = self.base_venv_path / package_name / version / stage
        return versioned_path
