from pydantic import BaseModel


class PackageRequestArgument(BaseModel):
    name: str
    value: str
