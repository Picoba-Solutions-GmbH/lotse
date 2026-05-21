from pydantic import BaseModel

from src.models.package_request_argument import PackageRequestArgument


class LiveCodeFile(BaseModel):
    name: str
    content: str


class LivePackageArgument(BaseModel):
    name: str
    default: str = ""


class LivePackage(BaseModel):
    package_name: str
    python_version: str
    files: list[LiveCodeFile]
    package_arguments: list[LivePackageArgument] = []


class LivePackageInfo(BaseModel):
    package_name: str
    python_version: str
    last_modified: str | None = None


class LiveRunRequest(BaseModel):
    arguments: list[PackageRequestArgument] = []
    wait_for_completion: bool = True
