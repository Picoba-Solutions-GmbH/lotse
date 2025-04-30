from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, String

from src.database.database_access import Base


class PackageEntity(Base):
    __tablename__ = 'Packages'
    __table_args__ = (
        CheckConstraint("stage IN ('dev', 'prod')", name="check_valid_stage"),
    )

    deployment_id = Column(String, primary_key=True)
    package_name = Column(String, nullable=False)
    python_version = Column(String, nullable=False)
    version = Column(String, nullable=False)
    stage = Column(String, nullable=False)
    description = Column(String, nullable=True)
    deployed_at = Column(DateTime, nullable=False)
    active = Column(Boolean, nullable=False, default=False)
    deleted = Column(Boolean, nullable=False, default=False)
    config = Column(String, nullable=True)
