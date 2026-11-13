from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.database.models.git_source_entity import GitSourceEntity


class GitSourceRepository:
    @staticmethod
    def create(db_session: Session, source: GitSourceEntity) -> GitSourceEntity:
        db_session.add(source)
        db_session.commit()
        return source

    @staticmethod
    def get(db_session: Session, source_id: str) -> GitSourceEntity | None:
        return db_session.query(GitSourceEntity).filter(GitSourceEntity.id == source_id).first()

    @staticmethod
    def get_by_package(db_session: Session, package_name: str) -> GitSourceEntity | None:
        return db_session.query(GitSourceEntity).filter(GitSourceEntity.package_name == package_name).first()

    @staticmethod
    def list_all(db_session: Session, package_names: set[str] | None = None) -> list[GitSourceEntity]:
        query = db_session.query(GitSourceEntity)
        if package_names is not None:
            query = query.filter(GitSourceEntity.package_name.in_(package_names))
        return query.order_by(GitSourceEntity.package_name).all()

    @staticmethod
    def list_due(db_session: Session, now: datetime) -> list[GitSourceEntity]:
        """Sources whose poll interval has elapsed since the last check."""
        return [
            source for source in db_session.query(GitSourceEntity).all()
            if source.last_checked_at is None
            or source.last_checked_at + timedelta(seconds=source.poll_interval_seconds) <= now  # type: ignore
        ]

    @staticmethod
    def delete(db_session: Session, source: GitSourceEntity) -> None:
        db_session.delete(source)
        db_session.commit()
