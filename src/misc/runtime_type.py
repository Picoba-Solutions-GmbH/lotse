from enum import Enum


class RuntimeType(str, Enum):
    PYTHON = "python"
    BINARY = "binary"
