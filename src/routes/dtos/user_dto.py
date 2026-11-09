from pydantic import BaseModel, Field

from src.authentication.roles_type import RoleType
from src.models.package_permissions import PackagePermissions


class UserResponse(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    email: str | None = None
    role: RoleType
    is_ldap: bool = False


class UserLookupResponse(BaseModel):
    id: str
    name: str
    display_name: str | None = None


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1)
    password: str = Field(min_length=6)
    role: RoleType = RoleType.USER
    display_name: str | None = None
    email: str | None = None


class UpdateUserRequest(BaseModel):
    role: RoleType | None = None
    password: str | None = Field(default=None, min_length=6)


class PackageShareResponse(BaseModel):
    user: UserLookupResponse
    can_execute: bool
    can_edit: bool


class PackageAccessResponse(BaseModel):
    package_name: str
    owner: UserLookupResponse | None = None
    permissions: PackagePermissions
    shares: list[PackageShareResponse] = []


class ShareRequest(BaseModel):
    can_execute: bool = False
    can_edit: bool = False


class OwnerRequest(BaseModel):
    user_id: str | None = None
