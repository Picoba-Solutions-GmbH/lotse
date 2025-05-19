import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.database.database_access import get_db_session
from src.database.models.package_entity import PackageEntity
from src.models.yaml_config import parse_config
from src.services.package_repository import PackageRepository
from src.utils.path_manager import PathManager


@dataclass
class PackageInfo:
    package_entity: PackageEntity
    package_dir: Path
    entry_point_path: Path
    requirements_path: Path


class PackageService:
    @staticmethod
    def get_package_info(
        package_name: str,
        stage: str,
        version: Optional[str]
    ) -> Optional[PackageInfo]:
        db_session = next(get_db_session())
        try:
            package_info = PackageRepository.get_package(db_session, package_name, stage, version)
            if not package_info:
                return None

            package_dir = PathManager.get_package_path(package_name, package_info.version, stage)
            if not package_dir.exists():
                return None

            config_content = parse_config(package_info.config)
            if not config_content:
                return None

            entry_file_path = os.path.join(package_dir, config_content.entrypoint)
            if os.path.exists(entry_file_path):
                return PackageInfo(
                    package_entity=package_info,
                    package_dir=Path(package_dir),
                    entry_point_path=Path(entry_file_path),
                    requirements_path=Path(os.path.join(package_dir, "requirements.txt"))
                )

            return None
        finally:
            db_session.close()

    @staticmethod
    def get_package_path(
        package_name: str,
        version: str,
        stage: str
    ) -> Optional[str]:
        package_dir = PathManager.get_package_path(package_name, version, stage)
        if not package_dir.exists():
            return None

        return str(package_dir)
