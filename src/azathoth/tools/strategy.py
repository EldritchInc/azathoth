"""Executable strategies backed by durable tool implementations."""

from pydantic import JsonValue

from azathoth.context import Context, active_step_lineage
from azathoth.revisions import content_digest
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
    StrategyResourceBinding,
)
from azathoth.tools.content import active_tool_content, content_input_files
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
        """Execute the resolved tool using workflow-bound inputs.

        Content inputs are given as files of the content their handles name,
        from the running step's content access (ADR 0114).
        """

        step = active_step_lineage()

        async with content_input_files(
            self._implementation,
            self._inputs_from_context(context),
            tool=self._metadata.name,
            access=active_tool_content(),
            run_id=step.step.run_id if step is not None else None,
        ) as inputs:
            output = await self._executor.execute(
                self._implementation,
                inputs,
            )

        return StrategyOutcome(
            output=output,
            resources=(
                StrategyResourceBinding(
                    kind="tool",
                    identifier=str(self._implementation.id),
                    attributes={
                        "tool_id": str(self._implementation.tool_id),
                        "tool_version": self._implementation.tool_version,
                        "runtime": self._implementation.runtime,
                        "implementation_digest": content_digest(self._implementation),
                    },
                ),
            ),
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
