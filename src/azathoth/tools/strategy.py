"""Executable strategies backed by durable tool implementations."""

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.tools.exceptions import ToolExecutionError
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.protocols import ToolExecutor

_WORKFLOW_INPUT_EVENT_TYPE = "workflow.input.bound"
_WORKFLOW_INPUT_EVENT_PRODUCER = "workflow-runner"


class ToolStrategy:
    """Execute one resolved durable tool implementation as a strategy."""

    def __init__(
        self,
        *,
        metadata: StrategyMetadata,
        implementation: ToolImplementation,
        executor: ToolExecutor,
    ) -> None:
        self._metadata = metadata
        self._implementation = implementation
        self._executor = executor

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
        """Execute the resolved tool using workflow-bound inputs."""

        output = await self._executor.execute(
            self._implementation,
            self._inputs_from_context(context),
        )

        return StrategyOutcome(
            output=output,
        )

    @staticmethod
    def _inputs_from_context(
        context: Context,
    ) -> dict[str, JsonValue]:
        """Return tool inputs bound into the current workflow step context."""

        inputs: dict[str, JsonValue] = {}

        for event in context.by_type(
            _WORKFLOW_INPUT_EVENT_TYPE,
        ):
            if event.producer != _WORKFLOW_INPUT_EVENT_PRODUCER:
                continue

            name = event.payload.get("name")

            if not isinstance(name, str) or not name:
                raise ToolExecutionError(
                    "Workflow-bound tool inputs require a non-empty string name."
                )

            if "value" not in event.payload:
                raise ToolExecutionError(
                    f"Workflow-bound tool input {name!r} is missing its value."
                )

            if name in inputs:
                raise ToolExecutionError(
                    f"Workflow-bound tool input {name!r} was bound more than once."
                )

            inputs[name] = event.payload["value"]

        return inputs
