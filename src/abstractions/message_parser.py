import json
from abc import abstractmethod
from typing import Protocol, runtime_checkable

from src.models.execution_request import ExecutionRequest


@runtime_checkable
class MessageParserProtocol(Protocol):
    @abstractmethod
    def parse_message(self, message: str) -> ExecutionRequest:
        ...


class JsonMessageParser(MessageParserProtocol):
    def parse_message(self, message: str) -> ExecutionRequest:
        data = json.loads(message)
        return ExecutionRequest(**data)
