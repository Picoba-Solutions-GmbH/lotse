from sqlalchemy import Boolean, Column, String

from src.database.database_access import Base


class UserEntity(Base):
    __tablename__ = 'Users'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_ldap = Column(Boolean, nullable=True, default=False)
    role = Column(String, nullable=False)
