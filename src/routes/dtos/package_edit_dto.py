from pydantic import BaseModel


class EnvironmentVariableDto(BaseModel):
    name: str
    # None keeps the stored value of a secret variable (its value is never sent to the client)
    value: str | None = ""
    # None decides by the variable name (e.g. *_KEY, *PASSWORD*, *TOKEN*)
    secret: bool | None = None
    # name the variable had when it was loaded, keeps a secret's value when it is renamed
    previous_name: str | None = None


class EnvironmentVariableViewDto(BaseModel):
    name: str
    # always None for secret variables
    value: str | None
    secret: bool
    has_value: bool


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
