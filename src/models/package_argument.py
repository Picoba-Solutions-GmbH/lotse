from typing import Literal, Optional, Union

from pydantic import BaseModel


class PackageArgument(BaseModel):
    name: str
    type: Literal["string", "number", "boolean"]
    default: Optional[Union[str, int, float, bool]] = None
    required: bool = False
    description: Optional[str] = None
