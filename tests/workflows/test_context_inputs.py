"""Tests for workflow inputs sourced from execution context."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_context_reference() -> WorkflowContextReference:
    """Create one deterministic external context reference."""

    return WorkflowContextReference(
        event_type="request.received",
        field_name="input",
    )


def create_step(
    *,
    inputs: tuple[WorkflowInputBinding, ...] = (),
) -> WorkflowStepSpecification:
    """Create one deterministic first workflow step."""

    return WorkflowStepSpecification(
        id=STEP_ID,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=STRATEGY_ID,
                name="Process request",
                description="Process externally supplied input.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Process the request.",
            ),
            model_selection=PortfolioModelSelection(
                requirements=ModelRequirements(),
            ),
        ),
        inputs=inputs,
    )


def test_workflow_context_reference_records_event_and_field() -> None:
    reference = create_context_reference()

    assert reference.event_type == "request.received"
    assert reference.field_name == "input"


def test_workflow_context_reference_rejects_empty_event_type() -> None:
    with pytest.raises(ValidationError):
        WorkflowContextReference(
            event_type="",
            field_name="input",
        )


def test_workflow_context_reference_rejects_empty_field_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowContextReference(
            event_type="request.received",
            field_name="",
        )


def test_workflow_context_reference_is_immutable() -> None:
    reference = create_context_reference()

    with pytest.raises(ValidationError):
        reference.field_name = "request"


def test_workflow_context_reference_round_trips_through_json() -> None:
    reference = create_context_reference()

    restored = WorkflowContextReference.model_validate_json(
        reference.model_dump_json(),
    )

    assert restored == reference


def test_workflow_input_binding_accepts_context_reference() -> None:
    reference = create_context_reference()

    binding = WorkflowInputBinding(
        name="request",
        source=reference,
    )

    assert binding.name == "request"
    assert binding.source == reference


def test_context_backed_input_binding_round_trips_through_json() -> None:
    binding = WorkflowInputBinding(
        name="request",
        source=create_context_reference(),
    )

    restored = WorkflowInputBinding.model_validate_json(
        binding.model_dump_json(),
    )

    assert restored == binding
    assert isinstance(
        restored.source,
        WorkflowContextReference,
    )


def test_first_step_can_consume_external_context() -> None:
    binding = WorkflowInputBinding(
        name="request",
        source=create_context_reference(),
    )

    step = create_step(
        inputs=(binding,),
    )

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="External request workflow",
            description="Consume caller input in the first workflow step.",
            version="1.0.0",
        ),
        steps=(step,),
    )

    assert workflow.steps == (step,)

    assert workflow.steps[0].inputs == (binding,)


def test_context_backed_input_does_not_require_workflow_dependency() -> None:
    step = create_step(
        inputs=(
            WorkflowInputBinding(
                name="request",
                source=create_context_reference(),
            ),
        ),
    )

    assert step.depends_on == ()

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="External request workflow",
            description="Consume external context without an upstream step.",
            version="1.0.0",
        ),
        steps=(step,),
    )

    assert workflow.steps[0].depends_on == ()
