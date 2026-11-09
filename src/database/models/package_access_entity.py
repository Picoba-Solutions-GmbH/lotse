from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        UniqueConstraint)

from src.database.database_access import Base
from src.database.models.user_entity import UserEntity


class PackageOwnershipEntity(Base):
    __tablename__ = 'PackageOwnership'

    package_name = Column(String, primary_key=True)
    owner_id = Column(String, ForeignKey(UserEntity.id, ondelete="SET NULL"), nullable=True)


class PackageShareEntity(Base):
    __tablename__ = 'PackageShares'
    __table_args__ = (UniqueConstraint('package_name', 'user_id', name='uq_package_share_user'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    package_name = Column(String, nullable=False, index=True)
    user_id = Column(String, ForeignKey(UserEntity.id, ondelete="CASCADE"), nullable=False, index=True)
    can_execute = Column(Boolean, nullable=False, default=False)
    can_edit = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
