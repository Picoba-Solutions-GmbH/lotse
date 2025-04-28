from enum import Enum


class PackageStatus(str, Enum):
    DEPLOYED = "deployed"
    RUNNING = "running"
    IDLE = "idle"
    DELETED = "deleted"
