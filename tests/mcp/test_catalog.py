"""Tests for the tool catalog built from the exposure document (ADR 0111)."""

import re
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.evaluation import json_schema_validator, json_schema_violations
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    InMemoryWorkflowProductionStateRepository,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from azathoth_mcp.catalog import (
    GET_INVOCATION_DESCRIPTION,
    GET_INVOCATION_SCHEMA,
    IDEMPOTENCY_KEY_SCHEMA,
    CatalogTool,
    ToolCatalog,
    ToolUnavailableError,
    UnknownToolError,
    check_exposure,
    unpromoted_workflows,
    workflow_tool_schema,
)
from azathoth_mcp.exposure import (
    ExposedWorkflow,
    ExposureDocument,
    ExposureDocumentError,
)

SUMMARIZE_ID = UUID("7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44")

TRIAGE_ID = UUID("0c9e6a52-5d1b-4f7e-8a3c-91b2d4e6f708")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

TICKET_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {"ticket": {"type": "string"}},
    "required": ["ticket"],
}


def production_state(
    workflow_id: UUID,
    *,
    model: str = "production-model",
) -> WorkflowProductionState:
    """Return a one-step production state for one workflow."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name=f"production-{workflow_id}",
                description="Exercise the tool catalog.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="catalog-prompt",
                            description="Exercise the tool catalog.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(text="Return success."),
                        model_selection=FixedModelSelection(
                            provider="test-provider",
                            model=model,
                        ),
                    ),
                ),
            ),
        ),
    )


def production(
    *workflow_ids: UUID,
) -> InMemoryWorkflowProductionStateRepository:
    """Return a production repository with an active state for some workflows."""

    repository = InMemoryWorkflowProductionStateRepository()

    for workflow_id in workflow_ids:
        repository.set(production_state(workflow_id))

    return repository


def exposure() -> ExposureDocument:
    """Return an exposure document offering two workflows."""

    return ExposureDocument(
        version=1,
        tools=(
            ExposedWorkflow(
                workflow_id=SUMMARIZE_ID,
                name="summarize_ticket",
                description="Summarize a support ticket in three sentences.",
                input_schema=TICKET_SCHEMA,
            ),
            ExposedWorkflow(
                workflow_id=TRIAGE_ID,
                name="triage",
                description="Triage a ticket.",
            ),
        ),
    )


def exposed_with(
    input_schema: JsonValue | None,
) -> ExposedWorkflow:
    """Return one exposed workflow with a given input schema."""

    return ExposedWorkflow(
        workflow_id=SUMMARIZE_ID,
        name="summarize_ticket",
        description="Summarize.",
        input_schema=input_schema,
    )


def violations(
    schema: dict[str, JsonValue],
    instance: JsonValue,
) -> tuple[str, ...]:
    """Return where one value violates one schema, as paths and messages."""

    return tuple(
        f"{violation.path}: {violation.message}"
        for violation in json_schema_violations(json_schema_validator(schema), instance)
    )


def test_every_exposed_workflow_is_one_tool_then_get_invocation() -> None:
    tools = ToolCatalog(exposure(), production(SUMMARIZE_ID, TRIAGE_ID)).tools()

    assert tools == (
        CatalogTool(
            name="summarize_ticket",
            description="Summarize a support ticket in three sentences.",
            input_schema=workflow_tool_schema(exposure().tools[0]),
            workflow_id=SUMMARIZE_ID,
        ),
        CatalogTool(
            name="triage",
            description="Triage a ticket.",
            input_schema=workflow_tool_schema(exposure().tools[1]),
            workflow_id=TRIAGE_ID,
        ),
        CatalogTool(
            name="get_invocation",
            description=GET_INVOCATION_DESCRIPTION,
            input_schema=GET_INVOCATION_SCHEMA,
        ),
    )


def test_a_workflow_tool_takes_the_input_and_an_optional_key() -> None:
    assert workflow_tool_schema(exposed_with(TICKET_SCHEMA)) == {
        "type": "object",
        "properties": {
            "input": TICKET_SCHEMA,
            "idempotency_key": IDEMPOTENCY_KEY_SCHEMA,
        },
        "required": ["input"],
        "additionalProperties": False,
    }


@pytest.mark.parametrize(
    ("input_schema", "written"),
    [(None, {}), (True, {}), (False, {"not": {}})],
)
def test_an_absent_or_boolean_input_schema_is_written_as_an_object(
    input_schema: JsonValue | None,
    written: JsonValue,
) -> None:
    properties = workflow_tool_schema(exposed_with(input_schema))["properties"]

    assert isinstance(properties, dict)
    assert properties["input"] == written


def test_every_tool_schema_is_valid_json_schema() -> None:
    for tool in ToolCatalog(exposure(), production()).tools():
        json_schema_validator(tool.input_schema)


def test_a_tool_schema_accepts_input_with_or_without_a_key() -> None:
    schema = workflow_tool_schema(exposed_with(TICKET_SCHEMA))

    assert violations(schema, {"input": {"ticket": "Printer is on fire."}}) == ()
    assert violations(schema, {"input": {"ticket": "x"}, "idempotency_key": "retry-1"}) == ()


def test_a_tool_schema_applies_the_operators_input_schema() -> None:
    schema = workflow_tool_schema(exposed_with(TICKET_SCHEMA))

    assert violations(schema, {"input": {}}) == ("$.input: 'ticket' is a required property",)


def test_a_tool_schema_requires_the_input_and_nothing_else() -> None:
    schema = workflow_tool_schema(exposed_with(None))

    assert violations(schema, {}) == ("$: 'input' is a required property",)
    assert violations(schema, {"input": None}) == ()
    assert violations(schema, {"input": 1, "workflow_id": "x"}) == (
        "$: Additional properties are not allowed ('workflow_id' was unexpected)",
    )


@pytest.mark.parametrize(
    "key",
    ["", "x" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1), "retry\n1", "retry\x00", "retry\x85"],
)
def test_a_tool_schema_refuses_a_key_the_job_envelope_would(
    key: str,
) -> None:
    schema = workflow_tool_schema(exposed_with(None))

    assert violations(schema, {"input": 1, "idempotency_key": key}) != ()


@pytest.mark.parametrize("key", ["x", "x" * MAX_IDEMPOTENCY_KEY_LENGTH, "retry é 1"])
def test_a_tool_schema_accepts_a_key_the_job_envelope_would(
    key: str,
) -> None:
    schema = workflow_tool_schema(exposed_with(None))

    assert violations(schema, {"input": 1, "idempotency_key": key}) == ()


def test_get_invocation_takes_exactly_an_invocation_id() -> None:
    assert violations(GET_INVOCATION_SCHEMA, {"invocation_id": str(SUMMARIZE_ID)}) == ()
    assert violations(GET_INVOCATION_SCHEMA, {}) == ("$: 'invocation_id' is a required property",)
    assert violations(GET_INVOCATION_SCHEMA, {"invocation_id": 1}) == (
        "$.invocation_id: 1 is not of type 'string'",
    )
    assert violations(GET_INVOCATION_SCHEMA, {"invocation_id": "x", "tool": "y"}) == (
        "$: Additional properties are not allowed ('tool' was unexpected)",
    )


def test_every_description_reaches_the_client_as_written() -> None:
    descriptions = {
        tool.name: tool.description for tool in ToolCatalog(exposure(), production()).tools()
    }

    assert descriptions["summarize_ticket"] == "Summarize a support ticket in three sentences."
    assert re.search(r"\binvocation ID\b", descriptions["get_invocation"])


def test_a_document_whose_workflows_are_all_active_is_accepted() -> None:
    check_exposure(exposure(), production(SUMMARIZE_ID, TRIAGE_ID))

    assert unpromoted_workflows(exposure(), production(SUMMARIZE_ID, TRIAGE_ID)) == ()


def test_a_workflow_with_no_active_state_stops_the_server() -> None:
    with pytest.raises(ExposureDocumentError) as raised:
        check_exposure(exposure(), production(TRIAGE_ID))

    assert str(raised.value) == (
        "Every exposed workflow must be active in production; these are not: "
        f'"summarize_ticket" ({SUMMARIZE_ID}). Promote each one before exposing it.'
    )


def test_every_workflow_with_no_active_state_is_named_in_document_order() -> None:
    with pytest.raises(ExposureDocumentError) as raised:
        check_exposure(exposure(), production())

    assert str(raised.value) == (
        "Every exposed workflow must be active in production; these are not: "
        f'"summarize_ticket" ({SUMMARIZE_ID}), "triage" ({TRIAGE_ID}). '
        "Promote each one before exposing it."
    )


def test_a_tool_is_found_with_its_active_state() -> None:
    states = production(SUMMARIZE_ID, TRIAGE_ID)
    catalog = ToolCatalog(exposure(), states)

    exposed, state = catalog.active_state("triage")

    assert exposed == exposure().tools[1]
    assert state == states.get(TRIAGE_ID)


def test_the_active_state_is_read_on_every_call() -> None:
    states = production(SUMMARIZE_ID)
    catalog = ToolCatalog(exposure(), states)

    _, first = catalog.active_state("summarize_ticket")

    states.set(production_state(SUMMARIZE_ID, model="promoted-again"))

    _, second = catalog.active_state("summarize_ticket")

    assert first != second
    assert second == production_state(SUMMARIZE_ID, model="promoted-again")


def test_a_tool_whose_workflow_is_no_longer_active_is_refused() -> None:
    catalog = ToolCatalog(exposure(), production(TRIAGE_ID))

    with pytest.raises(ToolUnavailableError) as raised:
        catalog.active_state("summarize_ticket")

    assert str(raised.value) == (
        'The tool "summarize_ticket" is not available: its workflow is no longer '
        "active in production."
    )


@pytest.mark.parametrize("name", ["summarize", "get_invocation", "SUMMARIZE_TICKET"])
def test_a_name_no_workflow_is_exposed_under_is_unknown(
    name: str,
) -> None:
    catalog = ToolCatalog(exposure(), production(SUMMARIZE_ID, TRIAGE_ID))

    with pytest.raises(UnknownToolError) as raised:
        catalog.active_state(name)

    assert str(raised.value) == f'There is no tool named "{name}".'


def test_only_exposed_workflows_are_reported_exposed() -> None:
    catalog = ToolCatalog(exposure(), production())

    assert catalog.is_exposed(SUMMARIZE_ID)
    assert catalog.is_exposed(TRIAGE_ID)
    assert not catalog.is_exposed(STEP_ID)


def test_the_catalog_keeps_its_exposure_document() -> None:
    assert ToolCatalog(exposure(), production()).exposure == exposure()
