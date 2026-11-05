"""The tool catalog: what the server offers, built from the exposure document (ADR 0111).

Each exposed workflow is one tool, under the name and description the
operator wrote, followed by the server's own `get_invocation`. A tool takes
an object holding the workflow's `input` and an optional `idempotency_key`;
the operator's input schema, if any, is the schema of `input`.

Promotion still decides what runs. The server refuses to start while an
exposed workflow has no active production state, and checks again on every
call, so a workflow that is no longer active is refused with a message the
model can read.
"""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.workflows import MAX_IDEMPOTENCY_KEY_LENGTH, WorkflowProductionState
from azathoth_mcp.exposure import (
    GET_INVOCATION_TOOL,
    ExposedWorkflow,
    ExposureDocument,
    ExposureDocumentError,
)

INPUT_ARGUMENT = "input"

IDEMPOTENCY_KEY_ARGUMENT = "idempotency_key"

INVOCATION_ID_ARGUMENT = "invocation_id"

IDEMPOTENCY_KEY_SCHEMA: dict[str, JsonValue] = {
    "type": "string",
    "minLength": 1,
    "maxLength": MAX_IDEMPOTENCY_KEY_LENGTH,
    "pattern": "^[^\\u0000-\\u001f\\u007f-\\u009f]*$",
    "description": (
        "Optional. A call repeated with the same key returns the recorded result "
        "instead of running the workflow again. Without one, the server makes a key "
        "and returns it with the result."
    ),
}
"""An idempotency key as the job envelope accepts it (ADR 0097)."""

GET_INVOCATION_DESCRIPTION = (
    "Return one invocation's result and its evidence: its runs, steps and revision, "
    "and who called. Takes the invocation ID that a tool call returned."
)

GET_INVOCATION_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {
        INVOCATION_ID_ARGUMENT: {
            "type": "string",
            "format": "uuid",
            "description": "The ID of the invocation to read.",
        },
    },
    "required": [INVOCATION_ID_ARGUMENT],
    "additionalProperties": False,
}


class ProductionStates(Protocol):
    """Where the catalog reads each workflow's active production state."""

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowProductionState | None:
        """Return the active production state for one workflow, if it has one."""

        ...


class CatalogTool(BaseModel):
    """One tool as a client sees it.

    An exposed workflow's tool names its workflow; the server's own tool
    names none.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, JsonValue]
    workflow_id: UUID | None = None


class UnknownToolError(LookupError):
    """Raised when a call names a tool the catalog does not offer."""


class ToolUnavailableError(RuntimeError):
    """Raised when an exposed workflow has no active production state any more."""


def workflow_tool_schema(
    exposed: ExposedWorkflow,
) -> dict[str, JsonValue]:
    """Return the input schema of one exposed workflow's tool.

    A boolean input schema is written as the object schema that means the
    same, since not every client reads boolean subschemas.
    """

    return {
        "type": "object",
        "properties": {
            INPUT_ARGUMENT: _object_schema(exposed.input_schema),
            IDEMPOTENCY_KEY_ARGUMENT: IDEMPOTENCY_KEY_SCHEMA,
        },
        "required": [INPUT_ARGUMENT],
        "additionalProperties": False,
    }


def unpromoted_workflows(
    exposure: ExposureDocument,
    production: ProductionStates,
) -> tuple[ExposedWorkflow, ...]:
    """Return every exposed workflow with no active production state, in document order."""

    return tuple(tool for tool in exposure.tools if production.get(tool.workflow_id) is None)


def check_exposure(
    exposure: ExposureDocument,
    production: ProductionStates,
) -> None:
    """Refuse an exposure document that lists a workflow not active in production.

    Raises:
        ExposureDocumentError: One or more exposed workflows have no active
            production state. Every one is named.
    """

    missing = unpromoted_workflows(exposure, production)

    if missing:
        raise ExposureDocumentError(
            "Every exposed workflow must be active in production; these are not: "
            + ", ".join(f'"{tool.name}" ({tool.workflow_id})' for tool in missing)
            + ". Promote each one before exposing it."
        )


class ToolCatalog:
    """The tools one server offers, and the active state behind each.

    The catalog reads production state on every lookup and keeps none, so a
    workflow promoted again is served at its new revision.
    """

    def __init__(
        self,
        exposure: ExposureDocument,
        production: ProductionStates,
    ) -> None:
        self._exposure = exposure
        self._production = production

    @property
    def exposure(self) -> ExposureDocument:
        """Return the exposure document the catalog was built from."""

        return self._exposure

    def tools(
        self,
    ) -> tuple[CatalogTool, ...]:
        """Return every tool, the exposed workflows in document order and then `get_invocation`."""

        return (
            *(
                CatalogTool(
                    name=exposed.name,
                    description=exposed.description,
                    input_schema=workflow_tool_schema(exposed),
                    workflow_id=exposed.workflow_id,
                )
                for exposed in self._exposure.tools
            ),
            CatalogTool(
                name=GET_INVOCATION_TOOL,
                description=GET_INVOCATION_DESCRIPTION,
                input_schema=GET_INVOCATION_SCHEMA,
            ),
        )

    def exposed(
        self,
        name: str,
    ) -> ExposedWorkflow:
        """Return the exposed workflow one tool name offers.

        Raises:
            UnknownToolError: No exposed workflow is offered under the name.
        """

        exposed = self._exposure.tool_named(name)

        if exposed is None:
            raise UnknownToolError(f'There is no tool named "{name}".')

        return exposed

    def active_state(
        self,
        name: str,
    ) -> tuple[ExposedWorkflow, WorkflowProductionState]:
        """Return one tool's exposed workflow and its active production state.

        Raises:
            UnknownToolError: No exposed workflow is offered under the name.
            ToolUnavailableError: The workflow has no active production state.
        """

        exposed = self.exposed(name)
        state = self._production.get(exposed.workflow_id)

        if state is None:
            raise ToolUnavailableError(
                f'The tool "{name}" is not available: its workflow is no longer '
                "active in production."
            )

        return exposed, state

    def is_exposed(
        self,
        workflow_id: UUID,
    ) -> bool:
        """Report whether one workflow is offered as a tool."""

        return any(tool.workflow_id == workflow_id for tool in self._exposure.tools)


def _object_schema(
    schema: JsonValue | None,
) -> JsonValue:
    """Return one input schema as an object schema; none accepts any value."""

    if schema is None or schema is True:
        return {}

    if schema is False:
        return {"not": {}}

    return schema


__all__ = [
    "GET_INVOCATION_DESCRIPTION",
    "GET_INVOCATION_SCHEMA",
    "IDEMPOTENCY_KEY_ARGUMENT",
    "IDEMPOTENCY_KEY_SCHEMA",
    "INPUT_ARGUMENT",
    "INVOCATION_ID_ARGUMENT",
    "CatalogTool",
    "ProductionStates",
    "ToolCatalog",
    "ToolUnavailableError",
    "UnknownToolError",
    "check_exposure",
    "unpromoted_workflows",
    "workflow_tool_schema",
]
