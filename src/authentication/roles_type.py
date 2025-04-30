from enum import Enum


class RoleType(str, Enum):
    UNAOTHORIZED = "Unauthorized"
    OPERATOR = "Operator"
    ADMIN = "Admin"
