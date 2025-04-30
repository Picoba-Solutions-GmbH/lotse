from typing import Union

from pydantic import BaseModel


class User(BaseModel):
    username: str
    role: str


class UserInDB(User):
    hashed_password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Union[str, None] = None
    role: Union[str, None] = None
