from pydantic import BaseModel

from src.authentication.roles_type import RoleType

SYSTEM_USER_ID = "system"


class Token(BaseModel):
    access_token: str
    token_type: str


class CurrentUser(BaseModel):
    id: str
    username: str
    role: RoleType
    display_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == RoleType.ADMIN

    @property
    def is_system(self) -> bool:
        return self.id == SYSTEM_USER_ID


SYSTEM_ADMIN = CurrentUser(id=SYSTEM_USER_ID, username="admin", role=RoleType.ADMIN, display_name="Admin")
