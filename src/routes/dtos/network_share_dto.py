from pydantic import BaseModel


class NetworkShareProvisionRequest(BaseModel):
    name: str
    share_path: str
    storage_size: str = "100Gi"
    namespace: str | None = None
    access_modes: list[str] = ["ReadWriteMany"]
    mount_options: list[str] = ["dir_mode=0777", "file_mode=0777"]
    secret_name: str | None = None
    secret_namespace: str = "default"
    username: str | None = None
    password: str | None = None


class NetworkShareUpdateRequest(BaseModel):
    name: str
    share_path: str
    storage_size: str = "100Gi"
    namespace: str | None = None
    access_modes: list[str] = ["ReadWriteMany"]
    mount_options: list[str] = ["dir_mode=0777", "file_mode=0777"]
    secret_mode: str = "keep"
    secret_name: str | None = None
    secret_namespace: str = "default"
    username: str | None = None
    password: str | None = None


class NetworkShareResponse(BaseModel):
    id: str
    name: str
    pvc_name: str
    pv_name: str
    secret_name: str
    namespace: str


class NetworkShareVolumeResponse(BaseModel):
    id: str
    name: str
    pvc_name: str

    class Config:
        from_attributes = True


class NetworkShareDetailResponse(BaseModel):
    id: str
    name: str
    pvc_name: str
    pv_name: str
    share_path: str
    storage_size: str
    namespace: str
    access_modes: list[str]
    mount_options: list[str]
    secret_name: str
    secret_namespace: str
    pv_status: str
    pvc_status: str


class NetworkShareTestResponse(BaseModel):
    success: bool
    message: str
    output: str | None = None
