from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.database.models.image_source_entity import ImageSourceEntity


class ImageSourceRepository:
    @staticmethod
    def create(db_session: Session, source: ImageSourceEntity) -> ImageSourceEntity:
        db_session.add(source)
        db_session.commit()
        return source

    @staticmethod
    def get(db_session: Session, source_id: str) -> ImageSourceEntity | None:
        return db_session.query(ImageSourceEntity).filter(ImageSourceEntity.id == source_id).first()

    @staticmethod
    def get_by_package(db_session: Session, package_name: str) -> ImageSourceEntity | None:
        return db_session.query(ImageSourceEntity).filter(ImageSourceEntity.package_name == package_name).first()

    @staticmethod
    def list_all(db_session: Session, package_names: set[str] | None = None,
                 registry_id: str | None = None) -> list[ImageSourceEntity]:
        query = db_session.query(ImageSourceEntity)
        if package_names is not None:
            query = query.filter(ImageSourceEntity.package_name.in_(package_names))
        if registry_id is not None:
            query = query.filter(ImageSourceEntity.registry_id == registry_id)
        return query.order_by(ImageSourceEntity.package_name).all()

    @staticmethod
    def list_due(db_session: Session, now: datetime) -> list[ImageSourceEntity]:
        return [
            source for source in db_session.query(ImageSourceEntity).all()
            if source.last_checked_at is None
            or source.last_checked_at + timedelta(seconds=source.poll_interval_seconds) <= now  # type: ignore
        ]

    @staticmethod
    def delete(db_session: Session, source: ImageSourceEntity) -> None:
        db_session.delete(source)
        db_session.commit()
