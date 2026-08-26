"""Tests for prompt-backed workflow model selection authority."""

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    FixedModelSelection,
    PortfolioModelSelection,
)
from azathoth.providers import (
    ModelCapability,
    ModelRequirements,
)


def test_portfolio_model_selection_preserves_model_requirements() -> None:
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
                ModelCapability.TOOL_USE,
            }
        ),
        minimum_context_window_tokens=128_000,
    )

    selection = PortfolioModelSelection(
        requirements=requirements,
    )

    assert selection.requirements == requirements


def test_fixed_model_selection_derives_provider_qualified_identifier() -> None:
    selection = FixedModelSelection(
        provider="example-provider",
        model="example-model",
    )

    assert selection.identifier == "example-provider/example-model"


def test_fixed_model_selection_does_not_persist_derived_identifier() -> None:
    selection = FixedModelSelection(
        provider="example-provider",
        model="example-model",
    )

    assert selection.model_dump() == {
        "provider": "example-provider",
        "model": "example-model",
    }


def test_portfolio_model_selection_is_immutable() -> None:
    selection = PortfolioModelSelection(
        requirements=ModelRequirements(),
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        selection.requirements = ModelRequirements(
            minimum_context_window_tokens=128_000,
        )


def test_fixed_model_selection_is_immutable() -> None:
    selection = FixedModelSelection(
        provider="example-provider",
        model="example-model",
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        selection.model = "replacement-model"
