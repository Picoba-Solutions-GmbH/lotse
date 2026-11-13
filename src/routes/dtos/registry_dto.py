from datetime import datetime

from pydantic import BaseModel, Field


class RegistrySettings(BaseModel):
    name: str
    # e.g. myacr.azurecr.io, ghcr.io/myorg (a path is used as discovery path)
    host: str
    provider: str = "generic"
    api_url: str | None = None
    username: str | None = None
    pull_secret_mode: str = "none"
    pull_secret_name: str | None = None
    discovery_path: str | None = None
    auto_register: bool = False
    default_auto_sync: bool = True
    poll_interval_seconds: int = Field(default=300, ge=60, le=86400)


class RegistryCreateRequest(RegistrySettings):
    token: str | None = None


class RegistryUpdateRequest(RegistrySettings):
    # None keeps the stored token
    token: str | None = None
    clear_token: bool = False


class RegistryTestRequest(BaseModel):
    host: str
    provider: str = "generic"
    api_url: str | None = None
    username: str | None = None
    token: str | None = None
    discovery_path: str | None = None
    # test an existing registry with its stored token when no token is given
    registry_id: str | None = None


class RegistryTestResponse(BaseModel):
    success: bool
    message: str
    repositories: list[str] = []


class RegistryResponse(BaseModel):
    id: str
    name: str
    host: str
    provider: str
    api_url: str | None = None
    username: str | None = None
    has_token: bool
    pull_secret_mode: str
    pull_secret_name: str | None = None
    # the imagePullSecret package pods get, None if the cluster pulls with its own access
    effective_pull_secret: str | None = None
    discovery_path: str | None = None
    auto_register: bool
    default_auto_sync: bool
    poll_interval_seconds: int
    last_discovered_at: datetime | None = None
    last_error: str | None = None
    image_source_count: int = 0
    created_at: datetime


class DiscoveredRepository(BaseModel):
    repository: str
    image: str
    package_name: str
    # package of the image source for this repository, if there is one
    registered_as: str | None = None
    # the suggested package name is already connected to another source
    name_taken: bool = False


class DiscoverResponse(BaseModel):
    created: list[str]
    registry: RegistryResponse
