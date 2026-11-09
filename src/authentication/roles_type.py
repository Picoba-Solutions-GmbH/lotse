from enum import Enum


class RoleType(str, Enum):
    USER = "User"
    ADMIN = "Admin"


_LEGACY_ROLES = {
    "Operator": RoleType.USER,
    "Unauthorized": RoleType.USER,
}


def parse_role(raw_role: str | None) -> RoleType:
    if raw_role is None:
        return RoleType.USER

    if raw_role in _LEGACY_ROLES:
        return _LEGACY_ROLES[raw_role]

    try:
        return RoleType(raw_role)
    except ValueError:
        return RoleType.USER
