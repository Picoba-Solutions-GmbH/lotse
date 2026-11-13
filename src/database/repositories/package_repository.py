import uuid
from datetime import datetime

from sqlalchemy import and_, update
from sqlalchemy.orm import Session

from src.database.models.package_entity import PackageEntity


class PackageRepository:
    @staticmethod
    def create_package(
        db_session: Session,
        package_name: str,
        version: str,
        python_version: str,
        config: str,
        description: str | None = None,
        set_as_active: bool = False,
        source_id: str | None = None,
        source_ref: str | None = None,
        source_commit: str | None = None
    ) -> PackageEntity:
        metadata = PackageEntity(
            deployment_id=str(uuid.uuid4()),
            package_name=package_name,
            python_version=python_version,
            version=version,
            description=description,
            deployed_at=datetime.now(),
            active=set_as_active,
            config=config,
            source_id=source_id,
            source_ref=source_ref,
            source_commit=source_commit
        )
        db_session.add(metadata)

        if set_as_active:
            db_session.execute(
                update(PackageEntity).where(  # type: ignore
                    and_(
                        PackageEntity.package_name == package_name,
                        PackageEntity.version != version,
                        PackageEntity.active
                    )
                ).values(active=False)
            )

        db_session.commit()
        return metadata

    @staticmethod
    def get_package_by_deployment_id(
        db_session: Session,
        deployment_id: str
    ) -> PackageEntity | None:
        return db_session.query(PackageEntity).filter(
            PackageEntity.deployment_id == deployment_id
        ).first()

    @staticmethod
    def get_package(
        db_session: Session,
        package_name: str,
        version: str | None = None
    ) -> PackageEntity | None:
        query = db_session.query(PackageEntity).filter(
            and_(
                PackageEntity.package_name == package_name,
                PackageEntity.deleted.is_(False),
            )
        )

        if version:
            query = query.filter(PackageEntity.version == version)
        else:
            query = query.filter(PackageEntity.active.is_(True))

        return query.first()

    @staticmethod
    def set_active_package(
        db_session: Session,
        package_name: str,
        version: str
    ) -> bool:
        package = PackageRepository.get_package(db_session, package_name, version)
        if not package:
            return False

        db_session.execute(
            update(PackageEntity).where(  # type: ignore
                and_(
                    PackageEntity.package_name == package_name,
                    PackageEntity.version != version
                )
            ).values(active=False)
        )
        package.active = True  # type: ignore
        db_session.commit()
        return True

    @staticmethod
    def list_packages(
        db_session: Session,
        package_name: str | None = None,
        version: str | None = None,
        package_names: set[str] | None = None
    ) -> list[PackageEntity]:
        query = db_session.query(PackageEntity).filter(
            PackageEntity.deleted.is_(False)
        )

        if package_names is not None:
            query = query.filter(PackageEntity.package_name.in_(package_names))

        if package_name:
            query = query.filter(PackageEntity.package_name == package_name)

        if version:
            query = query.filter(PackageEntity.version == version)

        return query.all()

    @staticmethod
    def delete_package(
        db_session: Session,
        package_name: str,
        version: str,
    ) -> bool:
        package = PackageRepository.get_package(db_session, package_name, version)
        if not package:
            return False

        db_session.execute(
            update(PackageEntity).where(  # type: ignore
                and_(
                    PackageEntity.package_name == package_name,
                    PackageEntity.version == version
                )
            ).values(deleted=True, active=False)
        )

        db_session.commit()
        return True

    @staticmethod
    def list_other_package_version(
        db_session: Session,
        package_name: str,
        version: str
    ) -> list[PackageEntity]:
        return db_session.query(PackageEntity).filter(
            and_(
                PackageEntity.package_name == package_name,
                PackageEntity.version != version,
                PackageEntity.deleted.is_(False)
            )
        ).all()

    @staticmethod
    def delete_other_package_versions(
        db_session: Session,
        package_name: str,
        version: str
    ) -> bool:
        db_session.execute(
            update(PackageEntity).where(  # type: ignore
                and_(
                    PackageEntity.package_name == package_name,
                    PackageEntity.version != version,
                    PackageEntity.deleted.is_(False)
                )
            ).values(deleted=True, active=False)
        )
        db_session.commit()
        return True

    @staticmethod
    def update_config(
        db_session: Session,
        package: PackageEntity,
        config: str
    ) -> PackageEntity:
        if package.original_config is None:
            package.original_config = package.config  # type: ignore
        package.config = config  # type: ignore
        package.modified_at = datetime.now()  # type: ignore
        db_session.commit()
        return package

    @staticmethod
    def revert_config(
        db_session: Session,
        package: PackageEntity
    ) -> PackageEntity:
        if package.original_config is not None:
            package.config = package.original_config  # type: ignore
            package.original_config = None  # type: ignore
            package.modified_at = datetime.now() if package.is_modified else None  # type: ignore
            db_session.commit()
        return package

    @staticmethod
    def mark_file_modified(
        db_session: Session,
        package: PackageEntity,
        relative_path: str
    ) -> PackageEntity:
        modified_files = list(package.modified_files or [])  # type: ignore
        if relative_path not in modified_files:
            modified_files.append(relative_path)
            modified_files.sort()
        # assign a new list, in-place changes of JSON columns are not tracked
        package.modified_files = modified_files  # type: ignore
        package.modified_at = datetime.now()  # type: ignore
        db_session.commit()
        return package

    @staticmethod
    def unmark_file_modified(
        db_session: Session,
        package: PackageEntity,
        relative_path: str
    ) -> PackageEntity:
        modified_files = [f for f in (package.modified_files or []) if f != relative_path]  # type: ignore
        package.modified_files = modified_files or None  # type: ignore
        package.modified_at = datetime.now() if package.is_modified else None  # type: ignore
        db_session.commit()
        return package
