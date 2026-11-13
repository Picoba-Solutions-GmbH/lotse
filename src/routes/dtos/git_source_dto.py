from datetime import datetime

from pydantic import BaseModel, Field


class GitSourceSettings(BaseModel):
    repo_url: str
    path: str = ""
    tag_prefix: str = "v"
    username: str | None = None
    auto_sync: bool = True
    prune_previous: bool = False
    poll_interval_seconds: int = Field(default=120, ge=30, le=86400)


class GitSourceCreateRequest(GitSourceSettings):
    package_name: str
    token: str | None = None


class GitSourceUpdateRequest(GitSourceSettings):
    # None keeps the stored token
    token: str | None = None
    clear_token: bool = False


class GitConnectionTestRequest(BaseModel):
    repo_url: str
    tag_prefix: str = "v"
    username: str | None = None
    token: str | None = None
    # test an existing source with its stored token when no token is given
    source_id: str | None = None


class GitTagResponse(BaseModel):
    tag: str
    version: str
    commit: str
    deployed: bool = False
    active: bool = False


class GitConnectionTestResponse(BaseModel):
    success: bool
    message: str
    tags: list[GitTagResponse] = []


class GitSourceResponse(BaseModel):
    id: str
    package_name: str
    repo_url: str
    path: str
    tag_prefix: str
    username: str | None = None
    has_token: bool
    auto_sync: bool
    prune_previous: bool
    poll_interval_seconds: int
    status: str
    active_version: str | None = None
    latest_tag: str | None = None
    latest_version: str | None = None
    latest_commit: str | None = None
    last_synced_tag: str | None = None
    last_synced_commit: str | None = None
    last_synced_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_error: str | None = None
    webhook_path: str
    # only for users who can edit the package
    webhook_token: str | None = None
    can_edit: bool = False
    created_at: datetime


class GitSyncRequest(BaseModel):
    # None deploys the newest tag
    tag: str | None = None


class GitSyncResponse(BaseModel):
    action: str
    tag: str
    version: str
    commit: str
    source: GitSourceResponse
