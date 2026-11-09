from enum import Enum

from pydantic import BaseModel


class Permission(str, Enum):
    VIEW = "view"
    EXECUTE = "execute"
    EDIT = "edit"
    MANAGE = "manage"


class PackagePermissions(BaseModel):
    view: bool = False
    execute: bool = False
    edit: bool = False
    manage: bool = False

    def has(self, permission: Permission) -> bool:
        return getattr(self, permission.value)
