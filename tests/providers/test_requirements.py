"""Tests for language model workload requirements."""

import pytest
from pydantic import ValidationError

from azathoth.providers import (
    ModelCapability,
    ModelModality,
    ModelRequirements,
)


def test_requirements_default_to_text_input_and_output() -> None:
    requirements = ModelRequirements()

    assert requirements.required_input_modalities == frozenset({ModelModality.TEXT})
    assert requirements.required_output_modalities == frozenset({ModelModality.TEXT})
    assert requirements.required_capabilities == frozenset()


def test_requirements_record_capabilities_and_limits() -> None:
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
                ModelCapability.TOOL_USE,
            }
        ),
        required_input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        ),
        required_output_modalities=frozenset(
            {
                ModelModality.TEXT,
            }
        ),
        minimum_context_window_tokens=100_000,
        minimum_output_tokens=8_000,
        maximum_input_usd_per_million_tokens=2.0,
        maximum_output_usd_per_million_tokens=8.0,
        require_known_pricing=True,
    )

    assert requirements.required_capabilities == frozenset(
        {
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.TOOL_USE,
        }
    )
    assert requirements.minimum_context_window_tokens == 100_000
    assert requirements.minimum_output_tokens == 8_000
    assert requirements.maximum_input_usd_per_million_tokens == 2.0
    assert requirements.maximum_output_usd_per_million_tokens == 8.0
    assert requirements.require_known_pricing is True


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("minimum_context_window_tokens", 0),
        ("minimum_output_tokens", 0),
        ("maximum_input_usd_per_million_tokens", -0.01),
        ("maximum_output_usd_per_million_tokens", -0.01),
    ),
)
def test_requirements_reject_invalid_numeric_constraints(
    field_name: str,
    value: int | float,
) -> None:
    with pytest.raises(ValidationError):
        ModelRequirements.model_validate(
            {
                field_name: value,
            }
        )


def test_requirements_are_immutable() -> None:
    requirements = ModelRequirements(
        minimum_context_window_tokens=32_000,
    )

    with pytest.raises(ValidationError):
        requirements.minimum_context_window_tokens = 64_000


def test_requirements_round_trip_through_json() -> None:
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        ),
        required_input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        ),
        minimum_context_window_tokens=100_000,
        maximum_input_usd_per_million_tokens=2.0,
        require_known_pricing=True,
    )

    restored = ModelRequirements.model_validate_json(requirements.model_dump_json())

    assert restored == requirements


def test_requirements_do_not_require_known_pricing_by_default() -> None:
    requirements = ModelRequirements()

    assert requirements.require_known_pricing is False
    assert requirements.maximum_input_usd_per_million_tokens is None
    assert requirements.maximum_output_usd_per_million_tokens is None
