"""Tests for model-independent prompt strategy specifications."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    ModelCapability,
    ModelModality,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata


def create_specification() -> PromptStrategySpec:
    """Create a deterministic prompt strategy specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=UUID("45649565-a0f3-434b-9dc3-a7ec8ac1f812"),
            name="Structured support classification",
            description="Classify a support request using structured output.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text=("Classify the support request and return structured JSON."),
        ),
        model_requirements=ModelRequirements(
            required_capabilities=frozenset(
                {
                    ModelCapability.STRUCTURED_OUTPUT,
                }
            ),
            required_input_modalities=frozenset(
                {
                    ModelModality.TEXT,
                }
            ),
            required_output_modalities=frozenset(
                {
                    ModelModality.TEXT,
                }
            ),
            minimum_context_window_tokens=32_000,
        ),
    )


def test_prompt_strategy_spec_records_workload_definition() -> None:
    specification = create_specification()

    assert specification.metadata.name == ("Structured support classification")
    assert specification.prompt.text.startswith("Classify the support request")
    assert (
        ModelCapability.STRUCTURED_OUTPUT in specification.model_requirements.required_capabilities
    )
    assert specification.model_requirements.minimum_context_window_tokens == 32_000


def test_prompt_strategy_spec_does_not_contain_language_model() -> None:
    specification = create_specification()

    assert not hasattr(specification, "language_model")


def test_prompt_strategy_spec_contains_only_durable_configuration() -> None:
    assert set(PromptStrategySpec.model_fields) == {
        "metadata",
        "prompt",
        "model_requirements",
    }


def test_prompt_strategy_spec_requires_model_requirements() -> None:
    with pytest.raises(ValidationError):
        PromptStrategySpec.model_validate(
            {
                "metadata": StrategyMetadata(
                    name="Missing requirements",
                    description="Invalid specification used by a test.",
                ),
                "prompt": Prompt(
                    text="Return a result.",
                ),
            }
        )


def test_prompt_strategy_spec_is_immutable() -> None:
    specification = create_specification()

    with pytest.raises(ValidationError):
        specification.prompt = Prompt(
            text="Changed prompt.",
        )


def test_prompt_strategy_spec_round_trips_through_json() -> None:
    specification = create_specification()

    restored = PromptStrategySpec.model_validate_json(specification.model_dump_json())

    assert restored == specification


def test_prompt_strategy_spec_supports_default_text_requirements() -> None:
    specification = PromptStrategySpec(
        metadata=StrategyMetadata(
            name="Simple classification",
            description="Classify a text request.",
        ),
        prompt=Prompt(
            text="Classify the request.",
        ),
        model_requirements=ModelRequirements(),
    )

    assert specification.model_requirements.required_input_modalities == (
        frozenset({ModelModality.TEXT})
    )
    assert specification.model_requirements.required_output_modalities == (
        frozenset({ModelModality.TEXT})
    )
