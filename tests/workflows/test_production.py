"""Tests for durable workflow production state."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    FixedModelSelection,
    PortfolioModelSelection,
    PromptStrategySpec,
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
    WorkflowProductionModelSubstitution,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

PROMPT_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_PROMPT_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

TOOL_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")


def create_workflow(
    *,
    fixed: bool = True,
    include_tool: bool = False,
    include_second_prompt: bool = False,
) -> WorkflowSpecification:
    """Create one deterministic durable workflow specification."""

    model_selection = (
        FixedModelSelection(
            provider="test-provider",
            model="production-model",
        )
        if fixed
        else PortfolioModelSelection(
            requirements=ModelRequirements(),
        )
    )

    steps: list[WorkflowStepSpecification] = [
        WorkflowStepSpecification(
            id=PROMPT_STEP_ID,
            specification=PromptStrategySpec(
                metadata=StrategyMetadata(
                    id=STRATEGY_ID,
                    name="production-prompt",
                    description="Exercise production workflow state.",
                    version="1.0.0",
                ),
                prompt=Prompt(
                    text="Return success.",
                ),
                model_selection=model_selection,
            ),
        )
    ]

    if include_second_prompt:
        steps.append(
            WorkflowStepSpecification(
                id=SECOND_PROMPT_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=SECOND_STRATEGY_ID,
                        name="second-production-prompt",
                        description="Exercise second production prompt.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return another success.",
                    ),
                    model_selection=FixedModelSelection(
                        provider="test-provider",
                        model="second-production-model",
                    ),
                ),
            )
        )

    if include_tool:
        steps.append(
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="production-tool",
                        runtime="python",
                    ),
                ),
                depends_on=(PROMPT_STEP_ID,),
            )
        )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="production-workflow",
            description="Exercise durable production state.",
            version="1.0.0",
        ),
        steps=tuple(steps),
    )


def create_substitution(
    *,
    step_id: UUID = PROMPT_STEP_ID,
) -> WorkflowProductionModelSubstitution:
    """Create deterministic production model substitutions."""

    return WorkflowProductionModelSubstitution(
        step_id=step_id,
        substitutes=(
            FixedModelSelection(
                provider="fallback-provider",
                model="first-fallback",
            ),
            FixedModelSelection(
                provider="fallback-provider",
                model="second-fallback",
            ),
        ),
    )


def test_production_state_records_workflow_specification() -> None:
    specification = create_workflow()

    state = WorkflowProductionState(
        specification=specification,
    )

    assert state.specification is specification


def test_production_state_preserves_workflow_identity() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(),
    )

    assert state.specification.metadata.id == WORKFLOW_ID


def test_production_state_accepts_fixed_model_selection() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(),
    )

    prompt = state.specification.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    assert isinstance(
        prompt.model_selection,
        FixedModelSelection,
    )

    assert prompt.model_selection.identifier == ("test-provider/production-model")


def test_production_state_rejects_portfolio_model_selection() -> None:
    with pytest.raises(
        ValidationError,
        match=("Production workflow prompt steps must use FixedModelSelection"),
    ):
        WorkflowProductionState(
            specification=create_workflow(
                fixed=False,
            ),
        )


def test_production_state_allows_tool_steps() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(
            include_tool=True,
        ),
    )

    tool = state.specification.steps[1].specification

    assert isinstance(
        tool,
        ToolStepSpecification,
    )

    assert tool.requirement.name == "production-tool"


def test_production_model_substitution_preserves_order() -> None:
    substitution = create_substitution()

    assert tuple(model.identifier for model in substitution.substitutes) == (
        "fallback-provider/first-fallback",
        "fallback-provider/second-fallback",
    )


def test_production_model_substitution_rejects_empty_substitutes() -> None:
    with pytest.raises(
        ValidationError,
    ):
        WorkflowProductionModelSubstitution(
            step_id=PROMPT_STEP_ID,
            substitutes=(),
        )


def test_production_model_substitution_rejects_duplicate_models() -> None:
    fallback = FixedModelSelection(
        provider="fallback-provider",
        model="fallback",
    )

    with pytest.raises(
        ValidationError,
        match="Production model substitutes must be unique",
    ):
        WorkflowProductionModelSubstitution(
            step_id=PROMPT_STEP_ID,
            substitutes=(
                fallback,
                fallback,
            ),
        )


def test_production_state_accepts_explicit_model_substitutions() -> None:
    substitution = create_substitution()

    state = WorkflowProductionState(
        specification=create_workflow(),
        model_substitutions=(substitution,),
    )

    assert state.model_substitutions == (substitution,)


def test_production_state_rejects_substitution_for_unknown_step() -> None:
    with pytest.raises(
        ValidationError,
        match=("Production model substitutions must reference prompt-backed workflow steps"),
    ):
        WorkflowProductionState(
            specification=create_workflow(),
            model_substitutions=(
                create_substitution(
                    step_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                ),
            ),
        )


def test_production_state_rejects_substitution_for_tool_step() -> None:
    with pytest.raises(
        ValidationError,
        match=("Production model substitutions must reference prompt-backed workflow steps"),
    ):
        WorkflowProductionState(
            specification=create_workflow(
                include_tool=True,
            ),
            model_substitutions=(
                create_substitution(
                    step_id=TOOL_STEP_ID,
                ),
            ),
        )


def test_production_state_rejects_duplicate_substitution_step() -> None:
    substitution = create_substitution()

    with pytest.raises(
        ValidationError,
        match=("Production model substitutions must reference unique workflow steps"),
    ):
        WorkflowProductionState(
            specification=create_workflow(),
            model_substitutions=(
                substitution,
                substitution,
            ),
        )


def test_production_state_rejects_primary_as_substitute() -> None:
    with pytest.raises(
        ValidationError,
        match=("Production model substitutes cannot include the step's primary model"),
    ):
        WorkflowProductionState(
            specification=create_workflow(),
            model_substitutions=(
                WorkflowProductionModelSubstitution(
                    step_id=PROMPT_STEP_ID,
                    substitutes=(
                        FixedModelSelection(
                            provider="test-provider",
                            model="production-model",
                        ),
                    ),
                ),
            ),
        )


def test_production_state_allows_independent_step_substitutions() -> None:
    first = create_substitution()

    second = WorkflowProductionModelSubstitution(
        step_id=SECOND_PROMPT_STEP_ID,
        substitutes=(
            FixedModelSelection(
                provider="other-provider",
                model="second-fallback",
            ),
        ),
    )

    state = WorkflowProductionState(
        specification=create_workflow(
            include_second_prompt=True,
        ),
        model_substitutions=(
            first,
            second,
        ),
    )

    assert state.model_substitutions == (
        first,
        second,
    )


def test_production_state_is_immutable() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(),
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        state.specification = create_workflow()


def test_production_model_substitution_is_immutable() -> None:
    substitution = create_substitution()

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        substitution.step_id = SECOND_PROMPT_STEP_ID


def test_production_state_round_trips_through_json() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(
            include_tool=True,
        ),
        model_substitutions=(create_substitution(),),
    )

    restored = WorkflowProductionState.model_validate_json(
        state.model_dump_json(),
    )

    assert restored == state
