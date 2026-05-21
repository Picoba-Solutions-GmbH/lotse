from pydantic import BaseModel


class SyncExecutionResponse(BaseModel):
    success: bool
    output: str
    task_id: str
    error: str | None = ""
    execution_time: float | None = None
