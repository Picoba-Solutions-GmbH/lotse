from pydantic import BaseModel


class AsyncExecutionResponse(BaseModel):
    task_id: str
    message: str
    status: str
