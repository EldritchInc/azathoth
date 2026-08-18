"""Tests for workflow step specifications."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    ModelCapability,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowInputBinding,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

STEP_ID = UUID("7f8cc955-8cbf-407e-a902-7d8c8465696b")
DEPENDENCY_ONE_ID = UUID("aa2ff5c7-ac35-44e2-af83-caf0b88b95c1")
DEPENDENCY_TWO_ID = UUID("7f496d81-759b-45a3-91cb-f412abf17613")


def create_prompt_specification() -> PromptStrategySpec:
    """Create a deterministic prompt strategy specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            name="Classification",
            description="Classify the support request.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Classify the supplied support request.",
        ),
        model_requirements=ModelRequirements(
            required_capabilities=frozenset(
                {
                    ModelCapability.STRUCTURED_OUTPUT,
                }
            ),
            minimum_context_window_tokens=32_000,
        ),
    )


def create_step() -> WorkflowStepSpecification:
    """Create a deterministic prompt-backed workflow step."""

    return WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
    )


def test_workflow_step_records_identifier() -> None:
    step = create_step()

    assert step.id == STEP_ID


def test_workflow_step_preserves_strategy_specification() -> None:
    step = create_step()

    specification = step.specification

    assert isinstance(
        specification,
        PromptStrategySpec,
    )

    assert specification.metadata.name == "Classification"
    assert specification.prompt.text == ("Classify the supplied support request.")
    assert (
        ModelCapability.STRUCTURED_OUTPUT in specification.model_requirements.required_capabilities
    )
    assert specification.model_requirements.minimum_context_window_tokens == 32_000


def test_workflow_step_preserves_specification() -> None:
    specification = create_prompt_specification()

    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=specification,
    )

    assert step.specification == specification


def test_workflow_step_is_immutable() -> None:
    step = create_step()

    with pytest.raises(ValidationError):
        step.specification = PromptStrategySpec(
            metadata=StrategyMetadata(
                name="Changed",
                description="Changed description.",
            ),
            prompt=Prompt(
                text="Changed prompt.",
            ),
            model_requirements=ModelRequirements(),
        )


def test_workflow_step_identifier_is_immutable() -> None:
    step = create_step()

    with pytest.raises(ValidationError):
        step.id = UUID("e99a07a8-d6fc-45c7-bf63-62b5ebf25243")


def test_workflow_step_round_trips_through_json() -> None:
    step = create_step()

    restored = WorkflowStepSpecification.model_validate_json(step.model_dump_json())

    assert restored == step


def test_workflow_step_defaults_to_no_dependencies() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
    )

    assert step.depends_on == ()


def test_workflow_step_records_dependencies() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(
            DEPENDENCY_ONE_ID,
            DEPENDENCY_TWO_ID,
        ),
    )

    assert step.depends_on == (
        DEPENDENCY_ONE_ID,
        DEPENDENCY_TWO_ID,
    )


def test_workflow_step_preserves_dependency_order() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(
            DEPENDENCY_TWO_ID,
            DEPENDENCY_ONE_ID,
        ),
    )

    assert step.depends_on == (
        DEPENDENCY_TWO_ID,
        DEPENDENCY_ONE_ID,
    )


def test_workflow_step_dependencies_round_trip_through_json() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(
            DEPENDENCY_ONE_ID,
            DEPENDENCY_TWO_ID,
        ),
    )

    restored = WorkflowStepSpecification.model_validate_json(step.model_dump_json())

    assert restored == step
    assert restored.depends_on == (
        DEPENDENCY_ONE_ID,
        DEPENDENCY_TWO_ID,
    )


def test_workflow_step_dependencies_are_immutable() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(DEPENDENCY_ONE_ID,),
    )

    with pytest.raises(ValidationError):
        step.depends_on = (DEPENDENCY_TWO_ID,)


def test_workflow_step_records_output_bindings() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        outputs=(
            WorkflowValueBinding(
                name="classification",
                path=("category",),
            ),
            WorkflowValueBinding(
                name="confidence",
                path=("confidence",),
            ),
        ),
    )

    assert tuple(binding.name for binding in step.outputs) == (
        "classification",
        "confidence",
    )


def test_workflow_step_defaults_to_no_output_bindings() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
    )

    assert step.outputs == ()


def test_workflow_step_records_input_bindings() -> None:
    binding = WorkflowInputBinding(
        name="classification",
        source=WorkflowValueReference(
            producer_step_id=DEPENDENCY_ONE_ID,
            name="classification",
        ),
    )

    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(DEPENDENCY_ONE_ID,),
        inputs=(binding,),
    )

    assert step.inputs == (binding,)


def test_workflow_step_defaults_to_no_input_bindings() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
    )

    assert step.inputs == ()
