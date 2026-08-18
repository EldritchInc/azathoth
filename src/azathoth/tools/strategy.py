"""Executable strategies backed by durable tool implementations."""

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.protocols import ToolExecutor


class ToolStrategy:
    """Execute one resolved durable tool implementation as a strategy."""

    def __init__(
        self,
        *,
        metadata: StrategyMetadata,
        implementation: ToolImplementation,
        executor: ToolExecutor,
        inputs: dict[str, JsonValue] | None = None,
    ) -> None:
        self._metadata = metadata
        self._implementation = implementation
        self._executor = executor
        self._inputs = inputs or {}

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable identifying metadata for this strategy."""

        return self._metadata

    @property
    def implementation(self) -> ToolImplementation:
        """Return the resolved tool implementation."""

        return self._implementation

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Execute the resolved tool implementation."""

        del context

        output = await self._executor.execute(
            self._implementation,
            self._inputs,
        )

        return StrategyOutcome(
            output=output,
        )
