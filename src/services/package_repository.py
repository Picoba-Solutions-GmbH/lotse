import uuid
from datetime import datetime
from typing import List, Optional

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
        stage: str,
        config: str,
        description: Optional[str] = None,
        set_as_active: bool = False
    ) -> PackageEntity:
        metadata = PackageEntity(
            deployment_id=str(uuid.uuid4()),
            package_name=package_name,
            python_version=python_version,
            version=version,
            stage=stage,
            description=description,
            deployed_at=datetime.now(),
            active=set_as_active,
            config=config
        )
        db_session.add(metadata)

        if set_as_active:
            db_session.execute(
                update(PackageEntity).where(  # type: ignore
                    and_(
                        PackageEntity.package_name == package_name,
                        PackageEntity.stage == stage,
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
    ) -> Optional[PackageEntity]:
        return db_session.query(PackageEntity).filter(
            PackageEntity.deployment_id == deployment_id
        ).first()

    @staticmethod
    def get_package(
        db_session: Session,
        package_name: str,
        stage: str,
        version: Optional[str] = None
    ) -> Optional[PackageEntity]:
        query = db_session.query(PackageEntity).filter(
            and_(
                PackageEntity.package_name == package_name,
                PackageEntity.stage == stage,
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
        version: str,
        stage: str
    ) -> bool:
        package = PackageRepository.get_package(db_session, package_name, stage, version)
        if not package:
            return False

        db_session.execute(
            update(PackageEntity).where(  # type: ignore
                and_(
                    PackageEntity.package_name == package_name,
                    PackageEntity.stage == stage,
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
        package_name: Optional[str] = None,
        stage: Optional[str] = None,
        version: Optional[str] = None
    ) -> List[PackageEntity]:
        query = db_session.query(PackageEntity).filter(
            PackageEntity.deleted.is_(False)
        )

        if package_name:
            query = query.filter(PackageEntity.package_name == package_name)

        if stage:
            query = query.filter(PackageEntity.stage == stage)

        if version:
            query = query.filter(PackageEntity.version == version)

        return query.all()

    @staticmethod
    def delete_package(
        db_session: Session,
        package_name: str,
        version: str,
        stage: str
    ) -> bool:
        package = PackageRepository.get_package(db_session, package_name, stage, version)
        if not package:
            return False

        db_session.execute(
            update(PackageEntity).where(  # type: ignore
                and_(
                    PackageEntity.package_name == package_name,
                    PackageEntity.version == version,
                    PackageEntity.stage == stage
                )
            ).values(deleted=True, active=False)
        )

        db_session.commit()
        return True

    @staticmethod
    def list_other_package_version(
        db_session: Session,
        package_name: str,
        stage: str,
        version: str
    ) -> List[PackageEntity]:
        return db_session.query(PackageEntity).filter(
            and_(
                PackageEntity.package_name == package_name,
                PackageEntity.stage == stage,
                PackageEntity.version != version,
                PackageEntity.deleted.is_(False)
            )
        ).all()

    @staticmethod
    def delete_other_package_versions(
        db_session: Session,
        package_name: str,
        stage: str,
        version: str
    ) -> bool:
        db_session.execute(
            update(PackageEntity).where(  # type: ignore
                and_(
                    PackageEntity.package_name == package_name,
                    PackageEntity.stage == stage,
                    PackageEntity.version != version,
                    PackageEntity.deleted.is_(False)
                )
            ).values(deleted=True, active=False)
        )
        db_session.commit()
        return True
