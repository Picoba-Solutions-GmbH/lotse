from typing import List, Optional

from pydantic import BaseModel, Field

from src.misc import constants
from src.models.package_request_argument import PackageRequestArgument


class ExecutionRequest(BaseModel):
    package_name: str
    version: Optional[str] = None
    stage: str = Field(..., pattern=constants.stage_regex_pattern)
    arguments: List[PackageRequestArgument] = []
    wait_for_completion: bool = True
