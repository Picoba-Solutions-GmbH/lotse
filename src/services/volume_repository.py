from typing import List, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.database.database_access import get_db_session
from src.database.models.volume_entity import VolumeEntity
from src.models.k8s.volume_map import VolumeMap
from src.models.yaml_config import Volume


class VolumeRepository:
    @staticmethod
    def create_volume(
        db_session: Session,
        volume_id: str,
        name: str,
        pvc_name: str,
    ) -> VolumeEntity:
        volume = VolumeEntity(
            id=volume_id,
            name=name,
            pvc_name=pvc_name
        )
        db_session.add(volume)
        db_session.commit()
        return volume

    @staticmethod
    def get_volume(
        db_session: Session,
        volume_id: str
    ) -> Optional[VolumeEntity]:
        return db_session.query(VolumeEntity).filter(
            VolumeEntity.id == volume_id
        ).first()

    @staticmethod
    def get_volume_maps(
        volumes: List[Volume]
    ) -> list[VolumeMap]:
        db_session = next(get_db_session())
        if len(volumes) == 0:
            return []

        volume_maps = []

        all_volumes = db_session.query(VolumeEntity).filter(
            VolumeEntity.name.in_([v.name for v in volumes])
        ).all()

        for volume in volumes:
            volume_entity = next((v for v in all_volumes if v.name == volume.name), None)
            if volume_entity:
                volume_map = VolumeMap(
                    name=volume_entity.name,
                    path=volume.path,
                    pvc_name=volume_entity.pvc_name
                )

                volume_maps.append(volume_map)

        return volume_maps

    @staticmethod
    def get_non_existing_volumes(
        volumes: List[Volume]
    ) -> list[str]:
        result = []
        db_session = next(get_db_session())
        if len(volumes) == 0:
            return []

        all_volumes = db_session.query(VolumeEntity).filter(
            VolumeEntity.name.in_([v.name for v in volumes])
        ).all()

        for volume in volumes:
            volume_entity = next((v for v in all_volumes if v.name == volume.name), None)
            if not volume_entity:
                result.append(volume.name)

        return result

    @staticmethod
    def list_volumes(
        db_session: Session,
    ) -> List[VolumeEntity]:
        return db_session.query(VolumeEntity).all()

    @staticmethod
    def update_volume(
        db_session: Session,
        volume_id: str,
        name: Optional[str] = None,
        pvc_name: Optional[str] = None
    ) -> Optional[VolumeEntity]:
        volume = db_session.query(VolumeEntity).filter(
            VolumeEntity.id == volume_id
        ).first()

        if volume:
            update_dict = {}
            if name is not None:
                update_dict["name"] = name
            if pvc_name is not None:
                update_dict["pvc_name"] = pvc_name

            if update_dict:
                db_session.execute(
                    update(VolumeEntity)
                    .where(VolumeEntity.id == volume_id)
                    .values(**update_dict)
                )
                db_session.commit()
                volume = db_session.query(VolumeEntity).filter(
                    VolumeEntity.id == volume_id
                ).first()

        return volume

    @staticmethod
    def delete_volume(
        db_session: Session,
        volume_id: str
    ) -> bool:
        volume = db_session.query(VolumeEntity).filter(
            VolumeEntity.id == volume_id
        ).first()
        if volume:
            db_session.delete(volume)
            db_session.commit()
            return True
        return False
