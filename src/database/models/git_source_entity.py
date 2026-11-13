from sqlalchemy import Boolean, Column, DateTime, Integer, String

from src.database.database_access import Base


class GitSourceEntity(Base):
    """A Git repository that Lotse watches. New tags are deployed as versions of `package_name`."""
    __tablename__ = 'GitSources'

    id = Column(String, primary_key=True)
    package_name = Column(String, nullable=False, unique=True)
    repo_url = Column(String, nullable=False)
    # folder inside the repository that holds config.yaml, "" for the repository root
    path = Column(String, nullable=False, default="")
    # tags "<prefix><semver>" are versions, e.g. prefix "v" -> tag v1.2.0 -> version 1.2.0
    tag_prefix = Column(String, nullable=False, default="v")
    username = Column(String, nullable=True)
    # name of the Kubernetes secret that holds the access token, None for public repositories
    credential_secret = Column(String, nullable=True)
    auto_sync = Column(Boolean, nullable=False, default=True)
    prune_previous = Column(Boolean, nullable=False, default=False)
    poll_interval_seconds = Column(Integer, nullable=False, default=120)
    webhook_token = Column(String, nullable=False)

    last_checked_at = Column(DateTime, nullable=True)
    latest_tag = Column(String, nullable=True)
    latest_commit = Column(String, nullable=True)
    last_synced_tag = Column(String, nullable=True)
    last_synced_commit = Column(String, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    # commit whose deployment failed for a reason that a retry won't fix (e.g. an invalid config.yaml).
    # Auto sync skips it until a new tag or commit appears.
    last_failed_commit = Column(String, nullable=True)

    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
