import uuid

from sqlalchemy import func, or_
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
        is_ldap: bool = False,
        display_name: str | None = None,
        email: str | None = None
    ) -> UserEntity:
        user = UserEntity(
            id=str(uuid.uuid4()),
            name=name,
            hashed_password=hashed_password,
            role=role.value,
            is_ldap=is_ldap,
            display_name=display_name,
            email=email
        )
        db_session.add(user)
        db_session.commit()
        return user

    @staticmethod
    def get_user_by_id(db_session: Session, user_id: str) -> UserEntity | None:
        return db_session.query(UserEntity).filter(UserEntity.id == user_id).first()

    @staticmethod
    def get_user_by_name(db_session: Session, name: str) -> UserEntity | None:
        return db_session.query(UserEntity).filter(
            func.lower(UserEntity.name) == name.lower()
        ).first()

    @staticmethod
    def list_users(db_session: Session) -> list[UserEntity]:
        return db_session.query(UserEntity).order_by(UserEntity.name).all()

    @staticmethod
    def search_users(db_session: Session, query: str, limit: int = 20) -> list[UserEntity]:
        pattern = f"%{query.lower()}%"
        return db_session.query(UserEntity).filter(
            or_(
                func.lower(UserEntity.name).like(pattern),
                func.lower(UserEntity.display_name).like(pattern),
                func.lower(UserEntity.email).like(pattern),
            )
        ).order_by(UserEntity.name).limit(limit).all()

    @staticmethod
    def count_admins(db_session: Session) -> int:
        return db_session.query(UserEntity).filter(UserEntity.role == RoleType.ADMIN.value).count()

    @staticmethod
    def update_user(
        db_session: Session,
        user_id: str,
        hashed_password: str | None = None,
        role: RoleType | None = None,
        display_name: str | None = None,
        email: str | None = None
    ) -> UserEntity | None:
        user = UserRepository.get_user_by_id(db_session, user_id)
        if not user:
            return None

        if hashed_password is not None:
            user.hashed_password = hashed_password  # type: ignore
        if role is not None:
            user.role = role.value  # type: ignore
        if display_name is not None:
            user.display_name = display_name  # type: ignore
        if email is not None:
            user.email = email  # type: ignore

        db_session.commit()
        return user

    @staticmethod
    def delete_user(db_session: Session, user_id: str) -> bool:
        user = UserRepository.get_user_by_id(db_session, user_id)
        if not user:
            return False

        db_session.delete(user)
        db_session.commit()
        return True

    @staticmethod
    def login_user(db_session: Session, name: str, password: str) -> UserEntity | None:
        user = UserRepository.get_user_by_name(db_session, name)
        if not user or user.is_ldap or not user.hashed_password:
            return None

        if verify_password(password, user.hashed_password):  # type: ignore
            return user

        return None
