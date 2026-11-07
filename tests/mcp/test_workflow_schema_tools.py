"""Tests that MCP tools take their promoted workflow's schemas (ADR 0118)."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import JsonValue

from azathoth.evaluation import json_schema_validator, json_schema_violations
from azathoth.jobs import JobErrorCode, JobStatus
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import WorkflowProductionState
from azathoth_mcp.access import STDIO_CALLER
from azathoth_mcp.catalog import (
    IDEMPOTENCY_KEY_SCHEMA,
    CatalogTool,
    effective_input_schema,
    workflow_output_schema,
)
from azathoth_mcp.exposure import ExposedWorkflow
from azathoth_mcp.server import build_server
from azathoth_mcp.service import ToolArgumentsError, ToolOutcome
from tests.mcp.test_server import call, listed, text_of
from tests.mcp.test_service import TICKET_SCHEMA, Harness
from tests.workflows.test_invocation_contract import contracted
from tests.workflows.test_production_invocation_service import WORKFLOW_ID

INPUT_SCHEMA: JsonValue = {
    "type": "object",
    "properties": {"ticket": {"type": "string"}, "priority": {"type": "integer"}},
    "required": ["ticket"],
}

ANSWER_SCHEMA: JsonValue = {"type": "string", "enum": ["deterministic response"]}

NUMBER_SCHEMA: JsonValue = {"type": "integer"}


def workflow_state(
    *,
    input_schema: JsonValue | None = INPUT_SCHEMA,
    output_schema: JsonValue | None = ANSWER_SCHEMA,
) -> WorkflowProductionState:
    """Return the contract tests' production state, emitting its result, with some schemas."""

    return contracted(input_schema=input_schema, output_schema=output_schema)


def served(
    tmp_path: Path,
    name: str,
    state: WorkflowProductionState,
) -> Harness:
    """Return a harness exposing a contracted workflow under some name.

    The harness's exposure gives `summarize` the operator's ticket schema,
    and any other name none.
    """

    repositories = open_repositories(tmp_path / "azathoth.db")
    repositories.production_states.set(state)

    return Harness(tmp_path / "azathoth.db", exposed=((WORKFLOW_ID, name),))


def tool_of(
    server: Harness,
) -> CatalogTool:
    """Return the one exposed workflow's tool."""

    (tool, _) = server.service.catalog.tools()

    return tool


def conforms(
    content: Any,
    schema: dict[str, JsonValue] | None,
) -> bool:
    """Return whether some structured content keeps an output schema."""

    assert schema is not None

    return not json_schema_violations(json_schema_validator(schema), content)


def exposed(
    input_schema: JsonValue | None = None,
) -> ExposedWorkflow:
    """Return an exposure of the contracted workflow, with or without the operator's schema."""

    return ExposedWorkflow(
        workflow_id=WORKFLOW_ID,
        name="triage",
        description="Triage a ticket.",
        input_schema=input_schema,
    )


# Input schemas


def test_the_operators_input_schema_wins_over_the_workflows() -> None:
    assert effective_input_schema(exposed(TICKET_SCHEMA), workflow_state()) == TICKET_SCHEMA


def test_without_the_operators_the_workflows_input_schema_is_used() -> None:
    assert effective_input_schema(exposed(), workflow_state()) == INPUT_SCHEMA


def test_without_either_no_input_schema_is_used() -> None:
    assert effective_input_schema(exposed(), workflow_state(input_schema=None)) is None
    assert effective_input_schema(exposed(), None) is None


def test_a_tool_lists_the_workflows_input_schema_without_the_operators(
    tmp_path: Path,
) -> None:
    assert tool_of(served(tmp_path, "triage", workflow_state())).input_schema["properties"] == {
        "input": INPUT_SCHEMA,
        "idempotency_key": IDEMPOTENCY_KEY_SCHEMA,
    }


def test_a_tool_lists_the_operators_input_schema_when_it_has_one(
    tmp_path: Path,
) -> None:
    assert tool_of(served(tmp_path, "summarize", workflow_state())).input_schema["properties"] == {
        "input": TICKET_SCHEMA,
        "idempotency_key": IDEMPOTENCY_KEY_SCHEMA,
    }


def test_a_workflow_promoted_with_new_schemas_is_listed_with_them(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "triage", workflow_state())

    server.repositories.production_states.set(
        workflow_state(input_schema=TICKET_SCHEMA, output_schema=NUMBER_SCHEMA)
    )

    tool = tool_of(server)

    assert tool.input_schema["properties"] == {
        "input": TICKET_SCHEMA,
        "idempotency_key": IDEMPOTENCY_KEY_SCHEMA,
    }
    assert tool.output_schema == workflow_output_schema(
        workflow_state(input_schema=TICKET_SCHEMA, output_schema=NUMBER_SCHEMA)
    )


def test_arguments_breaking_the_workflows_input_schema_are_refused_recording_nothing(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "triage", workflow_state())

    with pytest.raises(ToolArgumentsError) as raised:
        server.invoke("triage", {"input": {"priority": "high"}, "idempotency_key": "t-1"})

    assert str(raised.value) == (
        "The arguments of \"triage\" are not valid: $.input: 'ticket' is a required property; "
        "$.input.priority: 'high' is not of type 'integer'."
    )
    assert server.repositories.invocations.invocation_for_idempotency_key("t-1") is None
    assert server.loads == 0


def test_an_input_the_operators_schema_allows_is_still_held_to_the_workflows(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "summarize", workflow_state())

    outcome = server.invoke("summarize", {"input": {"ticket": "x", "priority": "high"}})

    assert outcome.status is JobStatus.FAILED
    assert outcome.error is not None
    assert outcome.error.code is JobErrorCode.INVALID_INPUT
    assert conforms(outcome.structured_content(), tool_of(server).output_schema)


# Output schemas


def result_schema(
    state: WorkflowProductionState | None,
) -> JsonValue:
    """Return the schema an outcome's `result` is held to, for one production state."""

    properties = workflow_output_schema(state)["properties"]

    assert isinstance(properties, dict)

    return properties["result"]


def emitting(
    schema: JsonValue,
) -> JsonValue:
    """Return the schema of a result that is null or the emission object, held to one schema."""

    return {
        "anyOf": [
            {"type": "object", "properties": {"result": schema}, "required": ["result"]},
            {"type": "null"},
        ]
    }


def test_an_outcomes_result_is_the_emission_held_to_the_output_schema() -> None:
    assert result_schema(workflow_state()) == emitting(ANSWER_SCHEMA)


@pytest.mark.parametrize(
    ("output_schema", "written"),
    [
        pytest.param(True, {}, id="true"),
        pytest.param(False, {"not": {}}, id="false"),
    ],
)
def test_a_boolean_output_schema_is_written_as_the_object_schema_it_means(
    output_schema: JsonValue,
    written: JsonValue,
) -> None:
    assert result_schema(workflow_state(output_schema=output_schema)) == emitting(written)


def test_without_an_output_schema_a_result_is_any_object() -> None:
    assert result_schema(workflow_state(output_schema=None)) == {
        "anyOf": [{"type": "object"}, {"type": "null"}]
    }
    assert result_schema(None) == result_schema(workflow_state(output_schema=None))


def test_an_outcome_names_exactly_its_fields_and_every_status_and_code() -> None:
    schema = workflow_output_schema(workflow_state())
    properties = schema["properties"]

    assert isinstance(properties, dict)
    assert schema["required"] == list(ToolOutcome.model_fields)
    assert list(properties) == list(ToolOutcome.model_fields)
    assert schema["additionalProperties"] is False
    assert {name: properties[name] for name in ("status", "replayed", "idempotency_key")} == {
        "status": {"type": "string", "enum": [status.value for status in JobStatus]},
        "replayed": {"type": "boolean"},
        "idempotency_key": {"type": "string"},
    }
    assert properties["invocation_id"] == {
        "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]
    }
    assert properties["error"] == {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": [code.value for code in JobErrorCode]},
                    "message": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "required": ["code", "message", "metadata"],
                "additionalProperties": False,
            },
            {"type": "null"},
        ]
    }
    assert {"invalid_input", "invalid_output"} <= {code.value for code in JobErrorCode}


def test_every_output_schema_is_valid_json_schema() -> None:
    for state in (None, workflow_state(), workflow_state(output_schema=False)):
        json_schema_validator(workflow_output_schema(state))


def test_a_succeeded_outcome_keeps_its_tools_output_schema(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "triage", workflow_state())

    outcome = server.invoke("triage", {"input": {"ticket": "x"}})

    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.result == {"result": "deterministic response"}
    assert conforms(outcome.structured_content(), tool_of(server).output_schema)


def test_a_result_breaking_the_output_schema_fails_and_keeps_the_tools_output_schema(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "triage", workflow_state(output_schema=NUMBER_SCHEMA))

    outcome = server.invoke("triage", {"input": {"ticket": "x"}})

    assert outcome.status is JobStatus.FAILED
    assert outcome.result is None
    assert outcome.error is not None
    assert outcome.error.code is JobErrorCode.INVALID_OUTPUT
    assert conforms(outcome.structured_content(), tool_of(server).output_schema)


def test_a_result_the_output_schema_refuses_does_not_keep_it(
    tmp_path: Path,
) -> None:
    succeeded = served(tmp_path, "triage", workflow_state()).invoke(
        "triage", {"input": {"ticket": "x"}}
    )

    assert not conforms(
        succeeded.structured_content(),
        workflow_output_schema(workflow_state(output_schema=NUMBER_SCHEMA)),
    )


# Through a client


def test_a_client_is_offered_each_workflow_tools_output_schema_and_none_for_get_invocation(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "triage", workflow_state())

    (tool, get_invocation) = listed(build_server(server.service, caller_of=lambda: STDIO_CALLER))

    assert tool.output_schema == workflow_output_schema(workflow_state())
    assert tool.input_schema == tool_of(server).input_schema
    assert get_invocation.name == "get_invocation"
    assert get_invocation.output_schema is None


def test_a_client_receives_structured_content_its_output_schema_allows(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "triage", workflow_state())
    mcp_server = build_server(server.service, caller_of=lambda: STDIO_CALLER)

    succeeded = call(mcp_server, "triage", {"input": {"ticket": "x"}})

    assert succeeded.is_error is False
    assert succeeded.structured_content is not None
    assert succeeded.structured_content["result"] == {"result": "deterministic response"}
    assert conforms(succeeded.structured_content, tool_of(server).output_schema)


def test_a_client_is_refused_an_input_breaking_the_workflows_schema_as_text(
    tmp_path: Path,
) -> None:
    server = served(tmp_path, "triage", workflow_state())

    refused = call(
        build_server(server.service, caller_of=lambda: STDIO_CALLER),
        "triage",
        {"input": {"ticket": 5}},
    )

    assert refused.is_error is True
    assert refused.structured_content is None
    assert text_of(refused) == (
        "The arguments of \"triage\" are not valid: $.input.ticket: 5 is not of type 'string'."
    )
