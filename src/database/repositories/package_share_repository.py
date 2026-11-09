from sqlalchemy.orm import Session

from src.database.models.package_access_entity import (PackageOwnershipEntity,
                                                        PackageShareEntity)


class PackageShareRepository:
    @staticmethod
    def get_owner_id(db_session: Session, package_name: str) -> str | None:
        ownership = db_session.get(PackageOwnershipEntity, package_name)
        return ownership.owner_id if ownership else None  # type: ignore

    @staticmethod
    def get_owner_map(db_session: Session) -> dict[str, str | None]:
        return {
            o.package_name: o.owner_id  # type: ignore
            for o in db_session.query(PackageOwnershipEntity).all()
        }

    @staticmethod
    def set_owner(db_session: Session, package_name: str, owner_id: str | None) -> None:
        ownership = db_session.get(PackageOwnershipEntity, package_name)
        if ownership:
            ownership.owner_id = owner_id  # type: ignore
        else:
            db_session.add(PackageOwnershipEntity(package_name=package_name, owner_id=owner_id))

        # The owner does not need an additional share entry.
        if owner_id:
            db_session.query(PackageShareEntity).filter(
                PackageShareEntity.package_name == package_name,
                PackageShareEntity.user_id == owner_id
            ).delete()

        db_session.commit()

    @staticmethod
    def get_share(db_session: Session, package_name: str, user_id: str) -> PackageShareEntity | None:
        return db_session.query(PackageShareEntity).filter(
            PackageShareEntity.package_name == package_name,
            PackageShareEntity.user_id == user_id
        ).first()

    @staticmethod
    def list_shares(db_session: Session, package_name: str) -> list[PackageShareEntity]:
        return db_session.query(PackageShareEntity).filter(
            PackageShareEntity.package_name == package_name
        ).all()

    @staticmethod
    def list_shares_for_user(db_session: Session, user_id: str) -> list[PackageShareEntity]:
        return db_session.query(PackageShareEntity).filter(
            PackageShareEntity.user_id == user_id
        ).all()

    @staticmethod
    def list_owned_package_names(db_session: Session, user_id: str) -> list[str]:
        rows = db_session.query(PackageOwnershipEntity.package_name).filter(
            PackageOwnershipEntity.owner_id == user_id
        ).all()
        return [row[0] for row in rows]

    @staticmethod
    def upsert_share(
        db_session: Session,
        package_name: str,
        user_id: str,
        can_execute: bool,
        can_edit: bool
    ) -> PackageShareEntity:
        share = PackageShareRepository.get_share(db_session, package_name, user_id)
        if share:
            share.can_execute = can_execute  # type: ignore
            share.can_edit = can_edit  # type: ignore
        else:
            share = PackageShareEntity(
                package_name=package_name,
                user_id=user_id,
                can_execute=can_execute,
                can_edit=can_edit
            )
            db_session.add(share)

        db_session.commit()
        return share

    @staticmethod
    def delete_share(db_session: Session, package_name: str, user_id: str) -> bool:
        deleted = db_session.query(PackageShareEntity).filter(
            PackageShareEntity.package_name == package_name,
            PackageShareEntity.user_id == user_id
        ).delete()
        db_session.commit()
        return deleted > 0

    @staticmethod
    def remove_user_access(db_session: Session, user_id: str) -> None:
        db_session.query(PackageShareEntity).filter(PackageShareEntity.user_id == user_id).delete()
        db_session.query(PackageOwnershipEntity).filter(
            PackageOwnershipEntity.owner_id == user_id
        ).update({PackageOwnershipEntity.owner_id: None})
        db_session.commit()
