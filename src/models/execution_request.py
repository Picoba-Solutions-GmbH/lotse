from pydantic import BaseModel

from src.models.package_request_argument import PackageRequestArgument


class ExecutionRequest(BaseModel):
    package_name: str
    version: str | None = None
    arguments: list[PackageRequestArgument] = []
    wait_for_completion: bool = True
