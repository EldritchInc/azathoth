"""Protocols implemented by Azathoth tool executors."""

from typing import Protocol

from pydantic import JsonValue

from azathoth.tools.implementation import ToolImplementation


class ToolExecutor(Protocol):
    """A service capable of executing durable tool implementations."""

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Execute a tool implementation with structured inputs."""

        ...
