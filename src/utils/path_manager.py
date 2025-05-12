import logging
import os
from pathlib import Path

from src.utils import config
from src.utils.name_generator import sanitize_name

logger = logging.getLogger(__name__)


class PathManager:
    @staticmethod
    def get_venv_path(package_name: str, version: str, stage: str) -> Path:
        sanitized_package_name = sanitize_name(package_name)
        versioned_path = Path(os.path.join(config.VENVS_ROOT, sanitized_package_name, version, stage))
        return versioned_path

    @staticmethod
    def get_package_path(package_name: str, version: str, stage: str) -> Path:
        sanitized_package_name = sanitize_name(package_name)
        package_path = Path(os.path.join(config.PACKAGES_ROOT, sanitized_package_name, version, stage))
        return package_path
