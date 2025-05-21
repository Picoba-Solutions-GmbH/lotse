import uuid
from typing import List, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.authentication.roles_type import RoleType
from src.database.models.user_entity import UserEntity
from src.utils.hasher import verify_password


class UserRepository:
    @staticmethod
    def create_user(
        db_session: Session,
        name: str,
        hashed_password: str,
        role: RoleType,
        is_ldap: bool = False
    ) -> UserEntity:
        user_id = str(uuid.uuid4())
        user = UserEntity(
            id=user_id,
            name=name,
            hashed_password=hashed_password,
            role=role,
            is_ldap=is_ldap
        )
        db_session.add(user)
        db_session.commit()
        return user

    @staticmethod
    def get_user_by_id(
        db_session: Session,
        user_id: str
    ) -> Optional[UserEntity]:
        return db_session.query(UserEntity).filter(
            UserEntity.id == user_id
        ).first()

    @staticmethod
    def get_user_by_name(
        db_session: Session,
        name: str
    ) -> Optional[UserEntity]:
        return db_session.query(UserEntity).filter(
            UserEntity.name == name
        ).first()

    @staticmethod
    def list_users(
        db_session: Session,
    ) -> List[UserEntity]:
        return db_session.query(UserEntity).all()

    @staticmethod
    def update_user(
        db_session: Session,
        user_id: str,
        name: Optional[str] = None,
        hashed_password: Optional[str] = None,
        role: Optional[str] = None,
        is_ldap: Optional[bool] = None
    ) -> Optional[UserEntity]:
        update_values = {}
        if name is not None:
            update_values['name'] = name
        if hashed_password is not None:
            update_values['hashed_password'] = hashed_password
        if role is not None:
            update_values['role'] = role
        if is_ldap is not None:
            update_values['is_ldap'] = is_ldap

        if update_values:
            db_session.execute(
                update(UserEntity)  # type: ignore
                .where(UserEntity.id == user_id)
                .values(**update_values)
            )
            db_session.commit()

        return UserRepository.get_user(db_session, user_id)

    @staticmethod
    def delete_user(
        db_session: Session,
        user_id: str
    ) -> bool:
        user = UserRepository.get_user(db_session, user_id)
        if user:
            db_session.delete(user)
            db_session.commit()
            return True
        return False

    @staticmethod
    def login_user(
        db_session: Session,
        name: str,
        password: str
    ) -> Optional[UserEntity]:
        user = db_session.query(UserEntity).filter(
            UserEntity.name == name
        ).first()

        if user and verify_password(password, user.hashed_password):
            return user

        return None

    @staticmethod
    def get_user(
        db_session: Session,
        name: str
    ) -> Optional[UserEntity]:
        user = db_session.query(UserEntity).filter(
            UserEntity.name == name
        ).first()
        return user
