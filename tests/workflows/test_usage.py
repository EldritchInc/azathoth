"""Tests for configured workflow model usage discovery."""

from uuid import UUID

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
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
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    workflow_uses_model,
    workflow_uses_tool,
    workflows_using_model,
    workflows_using_tool,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

THIRD_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

SECOND_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

THIRD_STEP_ID = UUID("66666666-6666-6666-6666-666666666666")

FIRST_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

SECOND_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")

MODEL_IDENTIFIER = "openrouter/example-model"
OTHER_MODEL_IDENTIFIER = "openrouter/other-model"
OTHER_TOOL_NAME = "sentiment"


def create_metadata(
    *,
    workflow_id: UUID,
    name: str,
) -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=workflow_id,
        name=name,
        description=f"{name} description.",
        version="1.0.0",
    )


def create_strategy_metadata(
    *,
    strategy_id: UUID,
    name: str,
) -> StrategyMetadata:
    """Create deterministic strategy metadata."""

    return StrategyMetadata(
        id=strategy_id,
        name=name,
        description=f"{name} description.",
        version="1.0.0",
    )


def create_fixed_prompt_workflow(
    *,
    workflow_id: UUID = FIRST_WORKFLOW_ID,
    model_identifier: str = MODEL_IDENTIFIER,
) -> WorkflowSpecification:
    """Create a workflow configured to one exact model."""

    provider, model = model_identifier.split(
        "/",
        maxsplit=1,
    )

    return WorkflowSpecification(
        metadata=create_metadata(
            workflow_id=workflow_id,
            name="Fixed prompt workflow",
        ),
        steps=(
            WorkflowStepSpecification(
                id=FIRST_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=create_strategy_metadata(
                        strategy_id=FIRST_STRATEGY_ID,
                        name="Fixed prompt",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider=provider,
                        model=model,
                    ),
                ),
            ),
        ),
    )


def create_context_prompt_workflow(
    *,
    workflow_id: UUID = SECOND_WORKFLOW_ID,
    model_identifier: str = MODEL_IDENTIFIER,
) -> WorkflowSpecification:
    """Create a context-aware workflow configured to one exact model."""

    provider, model = model_identifier.split(
        "/",
        maxsplit=1,
    )

    return WorkflowSpecification(
        metadata=create_metadata(
            workflow_id=workflow_id,
            name="Context prompt workflow",
        ),
        steps=(
            WorkflowStepSpecification(
                id=SECOND_STEP_ID,
                specification=ContextPromptStrategySpec(
                    metadata=create_strategy_metadata(
                        strategy_id=SECOND_STRATEGY_ID,
                        name="Context prompt",
                    ),
                    template=PromptTemplate(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider=provider,
                        model=model,
                    ),
                ),
            ),
        ),
    )


def create_portfolio_prompt_workflow() -> WorkflowSpecification:
    """Create a workflow that selects from an authorized portfolio."""

    return WorkflowSpecification(
        metadata=create_metadata(
            workflow_id=THIRD_WORKFLOW_ID,
            name="Portfolio workflow",
        ),
        steps=(
            WorkflowStepSpecification(
                id=THIRD_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=create_strategy_metadata(
                        strategy_id=FIRST_STRATEGY_ID,
                        name="Portfolio prompt",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_tool_workflow() -> WorkflowSpecification:
    """Create a workflow containing no configured model dependency."""

    return WorkflowSpecification(
        metadata=create_metadata(
            workflow_id=THIRD_WORKFLOW_ID,
            name="Tool workflow",
        ),
        steps=(
            WorkflowStepSpecification(
                id=THIRD_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                    ),
                ),
            ),
        ),
    )


def test_workflow_uses_fixed_model() -> None:
    workflow = create_fixed_prompt_workflow()

    assert workflow_uses_model(
        workflow,
        MODEL_IDENTIFIER,
    )


def test_context_workflow_uses_fixed_model() -> None:
    workflow = create_context_prompt_workflow()

    assert workflow_uses_model(
        workflow,
        MODEL_IDENTIFIER,
    )


def test_workflow_does_not_use_different_fixed_model() -> None:
    workflow = create_fixed_prompt_workflow()

    assert not workflow_uses_model(
        workflow,
        OTHER_MODEL_IDENTIFIER,
    )


def test_portfolio_selection_is_not_exact_model_usage() -> None:
    workflow = create_portfolio_prompt_workflow()

    assert not workflow_uses_model(
        workflow,
        MODEL_IDENTIFIER,
    )


def test_tool_workflow_does_not_use_model() -> None:
    workflow = create_tool_workflow()

    assert not workflow_uses_model(
        workflow,
        MODEL_IDENTIFIER,
    )


def test_workflows_using_model_returns_matching_workflows_in_order() -> None:
    first = create_fixed_prompt_workflow(
        workflow_id=FIRST_WORKFLOW_ID,
    )

    second = create_context_prompt_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
    )

    unrelated = create_fixed_prompt_workflow(
        workflow_id=THIRD_WORKFLOW_ID,
        model_identifier=OTHER_MODEL_IDENTIFIER,
    )

    assert workflows_using_model(
        (
            first,
            unrelated,
            second,
        ),
        MODEL_IDENTIFIER,
    ) == (
        first,
        second,
    )


def test_workflows_using_model_returns_empty_when_unused() -> None:
    assert (
        workflows_using_model(
            (
                create_portfolio_prompt_workflow(),
                create_tool_workflow(),
            ),
            MODEL_IDENTIFIER,
        )
        == ()
    )


def test_workflow_uses_required_tool() -> None:
    workflow = create_tool_workflow()

    assert workflow_uses_tool(
        workflow,
        "word_count",
    )


def test_workflow_does_not_use_different_tool() -> None:
    workflow = create_tool_workflow()

    assert not workflow_uses_tool(
        workflow,
        OTHER_TOOL_NAME,
    )


def test_prompt_workflow_does_not_use_tool() -> None:
    workflow = create_fixed_prompt_workflow()

    assert not workflow_uses_tool(
        workflow,
        "word_count",
    )


def test_workflows_using_tool_returns_matching_workflows_in_order() -> None:
    first = create_tool_workflow()

    unrelated = create_fixed_prompt_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
    )

    second = WorkflowSpecification(
        metadata=create_metadata(
            workflow_id=SECOND_WORKFLOW_ID,
            name="Second tool workflow",
        ),
        steps=(
            WorkflowStepSpecification(
                id=SECOND_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                    ),
                ),
            ),
        ),
    )

    assert workflows_using_tool(
        (
            first,
            unrelated,
            second,
        ),
        "word_count",
    ) == (
        first,
        second,
    )


def test_workflows_using_tool_returns_empty_when_unused() -> None:
    assert (
        workflows_using_tool(
            (
                create_fixed_prompt_workflow(),
                create_context_prompt_workflow(),
            ),
            "word_count",
        )
        == ()
    )
