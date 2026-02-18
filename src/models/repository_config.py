from pydantic import BaseModel, Field

from src.models.package_argument import PackageArgument


class RepositoryConfig(BaseModel):
    type: str
    name: str
    repo_url: str
    branch: str = "main"
    package_path: str = "main.py"
    organization: str
    project: str
    python_version: str = Field(default="3.9", pattern="^3\\.[6-9]|3\\.1[0-2]$")
    latest_pull_date: str | None = None
    env_content: str | None = None
    package_arguments: list[PackageArgument] | None = []
