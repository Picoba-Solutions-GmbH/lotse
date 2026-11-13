from datetime import datetime

from pydantic import BaseModel, Field


class ImageSourceSettings(BaseModel):
    registry_id: str
    # path inside the registry, e.g. lotse/order-service
    repository: str
    tag_prefix: str = ""
    auto_sync: bool = True
    prune_previous: bool = False
    poll_interval_seconds: int = Field(default=120, ge=30, le=86400)


class ImageSourceCreateRequest(ImageSourceSettings):
    # defaults to the last segment of the repository
    package_name: str | None = None


class ImageSourceUpdateRequest(ImageSourceSettings):
    pass


class ImageSourceResponse(BaseModel):
    id: str
    package_name: str
    registry_id: str
    registry_name: str | None = None
    repository: str
    image: str
    tag_prefix: str
    auto_sync: bool
    prune_previous: bool
    poll_interval_seconds: int
    status: str
    active_version: str | None = None
    latest_tag: str | None = None
    latest_version: str | None = None
    latest_digest: str | None = None
    last_synced_tag: str | None = None
    last_synced_digest: str | None = None
    last_synced_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_error: str | None = None
    webhook_path: str
    webhook_token: str | None = None
    can_edit: bool = False
    created_at: datetime


class ImageSyncRequest(BaseModel):
    tag: str | None = None


class ImageSyncResponse(BaseModel):
    action: str
    tag: str
    version: str
    digest: str
    source: ImageSourceResponse
