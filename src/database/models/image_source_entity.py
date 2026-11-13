from sqlalchemy import Boolean, Column, DateTime, Integer, String

from src.database.database_access import Base


class ImageSourceEntity(Base):
    """An image repository in a registry. New semver tags are deployed as versions of `package_name`."""
    __tablename__ = 'ImageSources'

    id = Column(String, primary_key=True)
    package_name = Column(String, nullable=False, unique=True)
    registry_id = Column(String, nullable=False)
    # path inside the registry, e.g. lotse/order-service
    repository = Column(String, nullable=False)
    tag_prefix = Column(String, nullable=False, default="")
    auto_sync = Column(Boolean, nullable=False, default=True)
    prune_previous = Column(Boolean, nullable=False, default=False)
    poll_interval_seconds = Column(Integer, nullable=False, default=120)
    webhook_token = Column(String, nullable=False)

    last_checked_at = Column(DateTime, nullable=True)
    latest_tag = Column(String, nullable=True)
    latest_digest = Column(String, nullable=True)
    last_synced_tag = Column(String, nullable=True)
    last_synced_digest = Column(String, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    # digest whose deployment failed for a reason a retry won't fix
    last_failed_digest = Column(String, nullable=True)

    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
