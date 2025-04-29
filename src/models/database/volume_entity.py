from sqlalchemy import Column, String

from src.models.database_access import Base


class VolumeEntity(Base):
    __tablename__ = 'Volumes'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    pvc_name = Column(String, nullable=False)
