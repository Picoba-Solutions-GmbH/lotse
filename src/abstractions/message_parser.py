import json
from typing import Protocol, runtime_checkable

from src.models.execution_request import ExecutionRequest


@runtime_checkable
class MessageParserProtocol(Protocol):
    def parse_message(self, message: str) -> ExecutionRequest:
        ...


class JsonMessageParser:
    def parse_message(self, message: str) -> ExecutionRequest:
        data = json.loads(message)
        return ExecutionRequest(**data)
