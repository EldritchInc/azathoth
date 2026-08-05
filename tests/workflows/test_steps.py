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
from azathoth.workflows import WorkflowStepSpecification

STEP_ID = UUID("7f8cc955-8cbf-407e-a902-7d8c8465696b")


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


def test_workflow_step_wraps_prompt_strategy_specification() -> None:
    step = create_step()

    assert step.specification.metadata.name == "Classification"
    assert step.specification.prompt.text == ("Classify the supplied support request.")
    assert (
        ModelCapability.STRUCTURED_OUTPUT
        in step.specification.model_requirements.required_capabilities
    )
    assert step.specification.model_requirements.minimum_context_window_tokens == 32_000


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
