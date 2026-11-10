from pydantic import BaseModel


class EnvironmentVariableDto(BaseModel):
    name: str
    value: str = ""


class PackageArgumentDto(BaseModel):
    name: str
    default: str = ""
    options: list[str] | None = None


class PackageFileDto(BaseModel):
    path: str
    size: int
    editable: bool
    modified: bool


class PackageFileContentDto(BaseModel):
    path: str
    content: str


class PackageFilePathDto(BaseModel):
    path: str
