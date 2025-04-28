from typing import Optional

from pydantic import BaseModel


class SyncExecutionResponse(BaseModel):
    success: bool
    output: str
    task_id: str
    error: Optional[str] = ""
