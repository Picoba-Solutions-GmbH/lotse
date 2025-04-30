from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String)
from sqlalchemy.orm import relationship

from src.database.database_access import Base
from src.database.models.package_entity import PackageEntity


class TaskEntity(Base):
    __tablename__ = "Tasks"

    task_id = Column(String, primary_key=True)
    deployment_id = Column(String, ForeignKey(PackageEntity.deployment_id), nullable=False)
    status = Column(String)
    stage = Column(String)
    result = Column(JSON, nullable=True)
    pid = Column(Integer, nullable=True)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    hostname = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    is_ui_app = Column(Boolean, nullable=False, default=False)
    ui_ip_address = Column(String, nullable=True)
    ui_port = Column(Integer, nullable=True)
    original_ui_port = Column(Integer, nullable=True)
    vscode_port = Column(Integer, nullable=True)

    package = relationship(PackageEntity, backref="tasks")
