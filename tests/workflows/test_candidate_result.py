"""Tests for carrying declared workflow results through candidates."""

from dataclasses import replace
from uuid import UUID

import pytest

from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    materialize_workflow_candidate,
)
from tests.model_authorization import (
    generate_model_substitutions,
    generate_workflow_candidate,
)
from tests.optimization.test_model_substitution import (
    STEP_ID,
    create_catalog,
    create_expensive_candidate,
    create_registry,
    create_workflow,
)

OTHER_STEP_ID = UUID("99999999-9999-4999-8999-999999999999")

RESULT = WorkflowValueReference(
    producer_step_id=STEP_ID,
    name="classification",
)


def create_resulting_workflow() -> WorkflowSpecification:
    """Create the substitution workflow with a declared result."""

    workflow = create_workflow()

    step = workflow.steps[0].model_copy(
        update={
            "outputs": (
                WorkflowValueBinding(
                    name="classification",
                ),
            ),
        }
    )

    return WorkflowSpecification(
        metadata=workflow.metadata,
        steps=(step,),
        result=RESULT,
    )


def create_resulting_candidate() -> WorkflowCandidate:
    """Create a candidate generated from the resulting workflow."""

    return create_expensive_candidate(
        workflow=create_resulting_workflow(),
        registry=create_registry(),
    )


def test_candidate_result_defaults_to_undeclared() -> None:
    candidate = create_expensive_candidate(
        workflow=create_workflow(),
        registry=create_registry(),
    )

    assert candidate.result is None


def test_generation_carries_declared_result() -> None:
    assert create_resulting_candidate().result == RESULT


def test_candidate_result_must_reference_candidate_step() -> None:
    with pytest.raises(
        ValueError,
        match="Workflow candidate result must reference a step in the same candidate.",
    ):
        replace(
            create_resulting_candidate(),
            result=WorkflowValueReference(
                producer_step_id=OTHER_STEP_ID,
                name="classification",
            ),
        )


def test_candidate_result_must_reference_declared_output() -> None:
    with pytest.raises(
        ValueError,
        match="Workflow candidate result must reference an output declared by its step.",
    ):
        replace(
            create_resulting_candidate(),
            result=WorkflowValueReference(
                producer_step_id=STEP_ID,
                name="summary",
            ),
        )


def test_model_substitution_preserves_declared_result() -> None:
    substitutions = generate_model_substitutions(
        specification=create_resulting_workflow(),
        candidate=create_resulting_candidate(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert substitutions
    assert all(substitution.result == RESULT for substitution in substitutions)


def test_materialization_preserves_declared_result() -> None:
    workflow = create_resulting_workflow()

    materialized = materialize_workflow_candidate(
        specification=workflow,
        candidate=create_resulting_candidate(),
    )

    assert materialized.result == RESULT


def test_materialization_rejects_candidate_with_different_result() -> None:
    workflow = create_resulting_workflow()

    candidate = generate_workflow_candidate(
        specification=workflow.model_copy(update={"result": None}),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    with pytest.raises(
        ValueError,
        match="Workflow specification and candidate must declare the same result.",
    ):
        materialize_workflow_candidate(
            specification=workflow,
            candidate=candidate,
        )
