from pydantic import BaseModel


class Metric(BaseModel):
    cpu: str
    memory: str
