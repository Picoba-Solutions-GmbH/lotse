from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.database.models.registry_entity import PullSecretMode, RegistryEntity
from src.services.registry import image_ref
from src.services.registry.secret_names import registry_secret_name


class RegistryRepository:
    @staticmethod
    def create(db_session: Session, registry: RegistryEntity) -> RegistryEntity:
        db_session.add(registry)
        db_session.commit()
        return registry

    @staticmethod
    def get(db_session: Session, registry_id: str) -> RegistryEntity | None:
        return db_session.query(RegistryEntity).filter(RegistryEntity.id == registry_id).first()

    @staticmethod
    def get_by_name(db_session: Session, name: str) -> RegistryEntity | None:
        return db_session.query(RegistryEntity).filter(RegistryEntity.name == name).first()

    @staticmethod
    def list_all(db_session: Session) -> list[RegistryEntity]:
        return db_session.query(RegistryEntity).order_by(RegistryEntity.name).all()

    @staticmethod
    def list_due_for_discovery(db_session: Session, now: datetime) -> list[RegistryEntity]:
        def due(registry: RegistryEntity) -> bool:
            if not registry.auto_register or registry.discovery_path is None:
                return False
            if registry.last_discovered_at is None:
                return True
            interval = timedelta(seconds=registry.poll_interval_seconds)  # type: ignore
            return registry.last_discovered_at + interval <= now  # type: ignore

        return [registry for registry in db_session.query(RegistryEntity).all() if due(registry)]

    @staticmethod
    def delete(db_session: Session, registry: RegistryEntity) -> None:
        db_session.delete(registry)
        db_session.commit()

    @staticmethod
    def find_for_image(db_session: Session, image: str) -> RegistryEntity | None:
        """Registry an image is pulled from. With several registries on the same host (e.g. ghcr.io for two
        organizations) the one with the longest matching discovery path wins."""
        try:
            ref = image_ref.parse(image)
        except ValueError:
            return None
        candidates = [r for r in RegistryRepository.list_all(db_session)
                      if image_ref.normalize_host(r.host) == ref.host]  # type: ignore

        def match_length(registry: RegistryEntity) -> int:
            path = (registry.discovery_path or "").strip("/").lower()  # type: ignore
            if not path:
                return 0
            return len(path) if ref.repository == path or ref.repository.startswith(path + "/") else -1

        candidates = [r for r in candidates if match_length(r) >= 0]
        return max(candidates, key=match_length) if candidates else None

    @staticmethod
    def pull_secrets_for(db_session: Session, image: str | None) -> list[str]:
        """imagePullSecrets for a pod running `image`."""
        if not image:
            return []
        registry = RegistryRepository.find_for_image(db_session, image)
        if registry is None:
            return []
        if registry.pull_secret_mode == PullSecretMode.LOTSE and registry.credential_secret:
            return [registry_secret_name(registry.id)]  # type: ignore
        if registry.pull_secret_mode == PullSecretMode.EXISTING and registry.pull_secret_name:
            return [str(registry.pull_secret_name)]
        return []
