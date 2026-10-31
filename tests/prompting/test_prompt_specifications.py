"""Tests for the single definition of the prompt specification kinds."""

from typing import get_args
from uuid import UUID

import azathoth.prompting
from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    ContextPromptStrategySpec,
    PortfolioModelSelection,
    PromptSpecification,
    PromptStrategySpec,
    PromptTemplate,
)
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowStepSpecification,
)


def create_metadata() -> StrategyMetadata:
    """Create deterministic strategy metadata."""

    return StrategyMetadata(
        id=UUID("6b1f3c2e-7d4a-4f0e-9a51-3c2d1e0f9a01"),
        name="Classify request",
        description="Classify one request.",
        version="1.0.0",
    )


def create_prompt_specification() -> PromptStrategySpec:
    """Create one fixed-prompt specification."""

    return PromptStrategySpec(
        metadata=create_metadata(),
        prompt=Prompt(text="Classify the request."),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )


def create_context_prompt_specification() -> ContextPromptStrategySpec:
    """Create one context-prompt specification."""

    return ContextPromptStrategySpec(
        metadata=create_metadata(),
        template=PromptTemplate(text="Classify the request."),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )


def test_prompt_specifications_lists_both_prompt_kinds() -> None:
    assert (
        PromptStrategySpec,
        ContextPromptStrategySpec,
    ) == PROMPT_SPECIFICATIONS


def test_prompt_specification_alias_matches_the_tuple() -> None:
    assert set(get_args(PromptSpecification)) == set(PROMPT_SPECIFICATIONS)


def test_every_non_tool_step_kind_is_a_prompt_specification() -> None:
    annotation = WorkflowStepSpecification.model_fields["specification"].annotation

    step_kinds = set(get_args(annotation))

    assert ToolStepSpecification in step_kinds
    assert step_kinds - {ToolStepSpecification} == set(PROMPT_SPECIFICATIONS)


def test_prompt_specifications_match_both_prompt_kinds() -> None:
    assert isinstance(
        create_prompt_specification(),
        PROMPT_SPECIFICATIONS,
    )
    assert isinstance(
        create_context_prompt_specification(),
        PROMPT_SPECIFICATIONS,
    )


def test_prompt_specifications_do_not_match_tool_steps() -> None:
    tool_step = ToolStepSpecification(
        requirement=ToolRequirement(name="word_count"),
    )

    assert not isinstance(
        tool_step,
        PROMPT_SPECIFICATIONS,
    )


def test_prompt_specifications_narrow_for_shared_attributes() -> None:
    specifications: tuple[object, ...] = (
        create_prompt_specification(),
        create_context_prompt_specification(),
        ToolStepSpecification(
            requirement=ToolRequirement(name="word_count"),
        ),
    )

    names = [
        specification.metadata.name
        for specification in specifications
        if isinstance(specification, PROMPT_SPECIFICATIONS)
    ]

    assert names == ["Classify request", "Classify request"]


def test_prompting_package_exports_the_definitions() -> None:
    assert "PROMPT_SPECIFICATIONS" in azathoth.prompting.__all__
    assert "PromptSpecification" in azathoth.prompting.__all__
