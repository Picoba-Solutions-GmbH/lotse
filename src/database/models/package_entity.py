from sqlalchemy import JSON, Boolean, Column, DateTime, String

from src.database.database_access import Base


class PackageEntity(Base):
    __tablename__ = 'Packages'

    deployment_id = Column(String, primary_key=True)
    package_name = Column(String, nullable=False)
    python_version = Column(String, nullable=False)
    version = Column(String, nullable=False)
    description = Column(String, nullable=True)
    deployed_at = Column(DateTime, nullable=False)
    active = Column(Boolean, nullable=False, default=False)
    deleted = Column(Boolean, nullable=False, default=False)
    config = Column(String, nullable=True)
    # config as deployed. Only set once the config was edited after deployment.
    original_config = Column(String, nullable=True)
    # relative paths of package files edited after deployment
    modified_files = Column(JSON, nullable=True)
    modified_at = Column(DateTime, nullable=True)

    @property
    def config_modified(self) -> bool:
        return self.original_config is not None and self.original_config != self.config

    @property
    def is_modified(self) -> bool:
        return self.config_modified or bool(self.modified_files)
