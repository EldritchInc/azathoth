"""Tests that a workflow declares the JSON Schemas of its input and its result (ADR 0118)."""

import warnings
from typing import Any

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.revisions import content_digest
from azathoth.workflows import (
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    WorkflowSpecification,
    materialize_workflow_candidate,
    promote_workflow_candidate,
)
from tests.workflows.test_promotion import WORKFLOW_ID, create_candidate, create_workflow

INPUT_SCHEMA: JsonValue = {
    "type": "object",
    "properties": {"ticket": {"type": "string"}},
    "required": ["ticket"],
}

OUTPUT_SCHEMA: JsonValue = {"type": "string", "enum": ["success"]}


def schemed(
    **schemas: JsonValue,
) -> WorkflowSpecification:
    """Return the promotion workflow declaring some schemas, validated as an import would."""

    return WorkflowSpecification.model_validate(
        {**create_workflow().model_dump(mode="json"), **schemas}
    )


def refusal(
    **fields: Any,
) -> str:
    """Return the message the promotion workflow with some fields is refused with."""

    with pytest.raises(ValidationError) as raised:
        WorkflowSpecification.model_validate(
            {**create_workflow().model_dump(mode="json"), **fields}
        )

    return str(raised.value.errors()[0]["msg"]).removeprefix("Value error, ")


def test_a_workflow_declares_no_schemas_by_default_and_serializes_as_it_always_has() -> None:
    workflow = create_workflow()
    dumped = workflow.model_dump(mode="json")

    assert (workflow.input_schema, workflow.output_schema) == (None, None)
    assert "input_schema" not in dumped
    assert "output_schema" not in dumped
    assert content_digest(WorkflowSpecification.model_validate(dumped)) == content_digest(workflow)


def test_a_workflow_with_schemas_round_trips_them() -> None:
    workflow = schemed(input_schema=INPUT_SCHEMA, output_schema=OUTPUT_SCHEMA)
    dumped = workflow.model_dump(mode="json")

    assert (dumped["input_schema"], dumped["output_schema"]) == (INPUT_SCHEMA, OUTPUT_SCHEMA)
    assert WorkflowSpecification.model_validate(dumped) == workflow
    assert content_digest(workflow) != content_digest(create_workflow())


@pytest.mark.parametrize(
    "schema",
    [
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(
            {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"},
            id="draft-07",
        ),
    ],
)
def test_any_valid_json_schema_may_be_declared(
    schema: JsonValue,
) -> None:
    assert schemed(input_schema=schema, output_schema=schema).input_schema == schema


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
@pytest.mark.parametrize(
    ("schema", "reason"),
    [
        pytest.param(3, "A JSON Schema must be an object or a boolean.", id="a-number"),
        pytest.param(
            {"type": "wat"},
            "Invalid JSON Schema: 'wat' is not valid under any of the given schemas",
            id="an-unknown-type",
        ),
    ],
)
def test_a_schema_that_is_not_one_is_refused_naming_which(
    field: str,
    schema: JsonValue,
    reason: str,
) -> None:
    label = field.replace("_", " ")

    assert refusal(**{field: schema}) == f"The workflow's {label} is not usable: {reason}"


def test_an_output_schema_needs_a_declared_result() -> None:
    assert refusal(result=None, output_schema=OUTPUT_SCHEMA) == (
        f"Workflow {WORKFLOW_ID} has an output schema, which describes its result, but "
        "declares no result."
    )


def test_an_input_schema_needs_no_result() -> None:
    assert schemed(result=None, input_schema=INPUT_SCHEMA).input_schema == INPUT_SCHEMA


def test_promotion_keeps_the_schemas_it_was_given() -> None:
    workflow = schemed(input_schema=INPUT_SCHEMA, output_schema=OUTPUT_SCHEMA)
    candidate = create_candidate(workflow)

    materialized = materialize_workflow_candidate(specification=workflow, candidate=candidate)
    revision = promote_workflow_candidate(
        specification=workflow,
        candidate=candidate,
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    assert (materialized.input_schema, materialized.output_schema) == (
        INPUT_SCHEMA,
        OUTPUT_SCHEMA,
    )
    assert (
        revision.state.specification.input_schema,
        revision.state.specification.output_schema,
    ) == (INPUT_SCHEMA, OUTPUT_SCHEMA)


def test_a_document_naming_no_schema_as_null_declares_none() -> None:
    workflow = schemed(input_schema=None, output_schema=None)

    assert (workflow.input_schema, workflow.output_schema) == (None, None)
    assert content_digest(workflow) == content_digest(create_workflow())


def test_a_workflow_dumps_as_python_values_without_warnings() -> None:
    workflow = schemed(input_schema=INPUT_SCHEMA)

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        dumped = workflow.model_dump()

    assert dumped["metadata"]["id"] == WORKFLOW_ID
    assert dumped["input_schema"] == INPUT_SCHEMA
    assert "output_schema" not in dumped
