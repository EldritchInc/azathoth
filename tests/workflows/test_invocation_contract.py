"""Tests that production invocations keep their workflow's declared schemas (ADR 0118)."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.providers import DeterministicLanguageModel, LanguageModelRegistry
from azathoth.workflows import (
    VIOLATIONS_METADATA_KEY,
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    WorkflowProductionEmission,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    input_contract_failure,
    invoke_production_workflow,
    output_contract_failure,
)
from tests.workflows.test_production_invocation_service import (
    PRIMARY,
    STEP_ID,
    WORKFLOW_ID,
    create_catalog,
    create_state,
)

INVOCATION_ID = UUID("c1710000-0000-4000-8000-000000000001")

INPUT_SCHEMA: JsonValue = {
    "type": "object",
    "properties": {"ticket": {"type": "string"}, "priority": {"type": "integer"}},
    "required": ["ticket"],
}

OUTPUT_SCHEMA: JsonValue = {"type": "string", "enum": ["success"]}


def test_a_value_that_keeps_its_schema_or_has_none_does_not_fail() -> None:
    assert (
        input_contract_failure(
            invocation_id=INVOCATION_ID, schema=INPUT_SCHEMA, received={"ticket": "x"}
        )
        is None
    )
    assert output_contract_failure(invocation_id=INVOCATION_ID, schema=None, result=3) is None


def test_an_input_that_breaks_its_schema_fails_naming_every_violation_in_order() -> None:
    assert input_contract_failure(
        invocation_id=INVOCATION_ID,
        schema=INPUT_SCHEMA,
        received={"priority": "high"},
    ) == ProductionInvocationFailure(
        invocation_id=INVOCATION_ID,
        error_code=ProductionInvocationErrorCode.INVALID_INPUT,
        message=(
            "The workflow's input does not match its input schema: $: 'ticket' is a "
            "required property; $.priority: 'high' is not of type 'integer'."
        ),
        metadata={
            VIOLATIONS_METADATA_KEY: [
                {"path": "$", "message": "'ticket' is a required property"},
                {"path": "$.priority", "message": "'high' is not of type 'integer'"},
            ]
        },
    )


def test_a_result_that_breaks_its_schema_fails_as_invalid_output() -> None:
    failure = output_contract_failure(
        invocation_id=INVOCATION_ID, schema=OUTPUT_SCHEMA, result="failure"
    )

    assert failure is not None
    assert failure.error_code is ProductionInvocationErrorCode.INVALID_OUTPUT
    assert failure.message == (
        "The workflow's result does not match its output schema: $: 'failure' is not one "
        "of ['success']."
    )


def test_the_codes_and_metadata_key_are_named() -> None:
    assert ProductionInvocationErrorCode.INVALID_OUTPUT.value == "invalid_output"
    assert VIOLATIONS_METADATA_KEY == "violations"


def contracted(
    *,
    input_schema: JsonValue | None = INPUT_SCHEMA,
    output_schema: JsonValue | None = OUTPUT_SCHEMA,
    emit_result: bool = True,
) -> WorkflowProductionState:
    """Return the service test's state, its answer declared and emitted, with schemas."""

    state = create_state()
    step = state.specification.steps[0].model_copy(
        update={"outputs": (WorkflowValueBinding(name="answer"),)}
    )
    specification = WorkflowSpecification.model_validate(
        {
            **state.specification.model_copy(update={"steps": (step,)}).model_dump(mode="json"),
            "result": {"producer_step_id": str(STEP_ID), "name": "answer"},
            "input_schema": input_schema,
            "output_schema": output_schema,
        }
    )

    return WorkflowProductionState(
        specification=specification,
        emissions=(
            (
                WorkflowProductionEmission(
                    name="result",
                    source=WorkflowValueReference(producer_step_id=STEP_ID, name="answer"),
                ),
            )
            if emit_result
            else (
                WorkflowProductionEmission(
                    name="answer",
                    source=WorkflowValueReference(producer_step_id=STEP_ID, name="answer"),
                ),
            )
        ),
    )


class Invoked:
    """One invocation of a contracted state, and the records it left."""

    def __init__(
        self,
        state: WorkflowProductionState,
        payload: JsonValue,
        *,
        answer: str = "success",
    ) -> None:
        self.invocations = InMemoryProductionInvocationRepository()
        self.runs = InMemoryWorkflowRunRepository()
        self.associations = InMemoryProductionInvocationRunRepository()
        self.result: ProductionInvocationResult = asyncio.run(
            invoke_production_workflow(
                workflow_id=WORKFLOW_ID,
                payload=payload,
                production_state=state,
                catalog=create_catalog(),
                registry=LanguageModelRegistry(
                    {
                        PRIMARY.identifier: DeterministicLanguageModel(
                            provider=PRIMARY.provider,
                            model=PRIMARY.model,
                            response_text=answer,
                        )
                    }
                ),
                invocation_repository=self.invocations,
                run_repository=self.runs,
                invocation_run_repository=self.associations,
            )
        )
        (self.invocation,) = self.invocations.invocations()


def test_an_invocation_that_keeps_its_contract_succeeds() -> None:
    invoked = Invoked(contracted(), {"ticket": "Refund order 0412."})

    assert invoked.result == ProductionInvocationSuccess(
        invocation_id=invoked.invocation.id, result={"result": "success"}
    )


def test_an_input_that_breaks_its_schema_fails_before_any_run_starts() -> None:
    invoked = Invoked(contracted(), {"priority": 1})

    assert isinstance(invoked.result, ProductionInvocationFailure)
    assert invoked.result.error_code is ProductionInvocationErrorCode.INVALID_INPUT
    assert invoked.result.message == (
        "The workflow's input does not match its input schema: $: 'ticket' is a required property."
    )
    assert invoked.invocations.result(invoked.invocation.id) == invoked.result
    assert invoked.associations.get(invoked.invocation.id) is None
    assert invoked.runs.runs() == ()


def test_a_result_that_breaks_its_schema_fails_and_keeps_the_run_that_made_it() -> None:
    invoked = Invoked(contracted(), {"ticket": "x"}, answer="failure")

    assert isinstance(invoked.result, ProductionInvocationFailure)
    assert invoked.result.error_code is ProductionInvocationErrorCode.INVALID_OUTPUT
    assert invoked.result.metadata == {
        VIOLATIONS_METADATA_KEY: [{"path": "$", "message": "'failure' is not one of ['success']"}]
    }
    assert invoked.invocations.result(invoked.invocation.id) == invoked.result

    association = invoked.associations.get(invoked.invocation.id)

    assert association is not None

    run = invoked.runs.get(association.run_id)

    assert run is not None
    assert not run.failed


@pytest.mark.parametrize(
    ("state", "payload", "answer"),
    [
        pytest.param(
            contracted(input_schema=None, output_schema=None), 3, "anything", id="no-schemas"
        ),
        pytest.param(contracted(input_schema=None), "any input", "success", id="no-input-schema"),
        pytest.param(
            contracted(output_schema=None), {"ticket": "x"}, "anything", id="no-output-schema"
        ),
    ],
)
def test_an_invocation_is_checked_only_against_the_schemas_its_workflow_declares(
    state: WorkflowProductionState,
    payload: JsonValue,
    answer: str,
) -> None:
    assert isinstance(Invoked(state, payload, answer=answer).result, ProductionInvocationSuccess)


def test_a_state_that_emits_no_result_has_no_result_to_check() -> None:
    invoked = Invoked(contracted(emit_result=False), {"ticket": "x"}, answer="failure")

    assert invoked.result == ProductionInvocationSuccess(
        invocation_id=invoked.invocation.id, result={"answer": "failure"}
    )
