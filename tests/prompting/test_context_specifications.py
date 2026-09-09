"""Tests for durable context-aware prompt strategy specifications."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import ModelRequirements
from azathoth.strategies import StrategyMetadata

STRATEGY_ID = UUID("11111111-1111-1111-1111-111111111111")


def create_metadata() -> StrategyMetadata:
    """Create deterministic strategy metadata."""

    return StrategyMetadata(
        id=STRATEGY_ID,
        name="Classify request",
        description="Classify an externally supplied request.",
        version="1.0.0",
    )


def create_template() -> PromptTemplate:
    """Create one context-dependent prompt template."""

    return PromptTemplate(
        text=("Classify this request as positive or negative.\n\nRequest: {request}"),
        bindings=(
            PromptBinding(
                variable_name="request",
                event_type="request.received",
                field_name="input",
            ),
        ),
    )


def test_context_prompt_specification_records_template() -> None:
    specification = ContextPromptStrategySpec(
        metadata=create_metadata(),
        template=create_template(),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )

    assert specification.metadata == create_metadata()
    assert specification.template == create_template()


def test_context_prompt_specification_records_portfolio_selection() -> None:
    selection = PortfolioModelSelection(
        requirements=ModelRequirements(),
    )

    specification = ContextPromptStrategySpec(
        metadata=create_metadata(),
        template=create_template(),
        model_selection=selection,
    )

    assert specification.model_selection == selection


def test_context_prompt_specification_records_fixed_selection() -> None:
    selection = FixedModelSelection(
        provider="openrouter",
        model="example-model",
    )

    specification = ContextPromptStrategySpec(
        metadata=create_metadata(),
        template=create_template(),
        model_selection=selection,
    )

    assert specification.model_selection == selection


def test_context_prompt_specification_is_immutable() -> None:
    specification = ContextPromptStrategySpec(
        metadata=create_metadata(),
        template=create_template(),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        specification.__setattr__(
            "template",
            PromptTemplate(
                text="Changed.",
            ),
        )


def test_context_prompt_specification_round_trips_through_json() -> None:
    specification = ContextPromptStrategySpec(
        metadata=create_metadata(),
        template=create_template(),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )

    restored = ContextPromptStrategySpec.model_validate_json(
        specification.model_dump_json(),
    )

    assert restored == specification
