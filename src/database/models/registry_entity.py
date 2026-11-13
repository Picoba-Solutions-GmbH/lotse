from sqlalchemy import Boolean, Column, DateTime, Integer, String

from src.database.database_access import Base


class RegistryProvider:
    GENERIC = "generic"
    ACR = "acr"
    GHCR = "ghcr"
    GITLAB = "gitlab"
    DOCKERHUB = "dockerhub"
    ALL = (GENERIC, ACR, GHCR, GITLAB, DOCKERHUB)


class PullSecretMode:
    # the cluster pulls with its own access (e.g. AKS attached to ACR)
    NONE = "none"
    # Lotse creates a kubernetes.io/dockerconfigjson secret from the credentials
    LOTSE = "lotse"
    # an existing pull secret in the package namespace
    EXISTING = "existing"
    ALL = (NONE, LOTSE, EXISTING)


class RegistryEntity(Base):
    """A container registry Lotse can list images of and pull them from."""
    __tablename__ = 'Registries'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    # e.g. myacr.azurecr.io, ghcr.io, registry.gitlab.com, docker.io
    host = Column(String, nullable=False)
    provider = Column(String, nullable=False, default=RegistryProvider.GENERIC)
    # API of GitLab / GitHub for listing images, None for the public default
    api_url = Column(String, nullable=True)
    username = Column(String, nullable=True)
    # Kubernetes secret (dockerconfigjson) with the credentials, None for anonymous access
    credential_secret = Column(String, nullable=True)
    pull_secret_mode = Column(String, nullable=False, default=PullSecretMode.NONE)
    # used with pull_secret_mode "existing"
    pull_secret_name = Column(String, nullable=True)

    # images below this path are packages, e.g. "lotse" or "myorg"
    discovery_path = Column(String, nullable=True)
    # create image sources for new images automatically
    auto_register = Column(Boolean, nullable=False, default=False)
    default_auto_sync = Column(Boolean, nullable=False, default=True)
    poll_interval_seconds = Column(Integer, nullable=False, default=300)

    last_discovered_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
