"""Tests for configured workflow model usage discovery."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.execution import ExecutionResult
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
from azathoth.strategies import (
    StrategyMetadata,
    StrategyResourceBinding,
)
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowProductionModelUsageRole,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    historical_model_usages,
    production_model_usages,
    production_uses_tool,
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
SUBSTITUTE_MODEL_IDENTIFIER = "openrouter/substitute-model"
SECOND_SUBSTITUTE_MODEL_IDENTIFIER = "openrouter/second-substitute-model"

TOOL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

OTHER_TOOL_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

IMPLEMENTATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

STARTED_AT = datetime(
    2026,
    9,
    13,
    20,
    0,
    tzinfo=UTC,
)

COMPLETED_AT = datetime(
    2026,
    9,
    13,
    20,
    0,
    1,
    tzinfo=UTC,
)


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


def create_execution_result(
    *,
    resources: tuple[StrategyResourceBinding, ...] = (),
    strategy_id: UUID = FIRST_STRATEGY_ID,
) -> ExecutionResult:
    """Create deterministic execution evidence with resource provenance."""

    context = Context()

    return ExecutionResult(
        strategy_id=strategy_id,
        strategy_name="Usage test strategy",
        strategy_version="1.0.0",
        output="OK",
        resources=resources,
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def create_attempt(
    *,
    attempt_number: int = 1,
    execution: ExecutionResult,
) -> WorkflowStepAttempt:
    """Create one deterministic successful workflow attempt."""

    return WorkflowStepAttempt(
        attempt_number=attempt_number,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        execution=execution,
    )


def create_step_run(
    *,
    step_id: UUID = FIRST_STEP_ID,
    execution: ExecutionResult | None = None,
    attempts: tuple[WorkflowStepAttempt, ...] | None = None,
) -> WorkflowStepRun:
    """Create one deterministic executed workflow step."""

    if attempts is None:
        resolved_execution = execution if execution is not None else create_execution_result()

        resolved_attempts = (
            create_attempt(
                execution=resolved_execution,
            ),
        )
    else:
        if not attempts:
            raise ValueError("Executed usage-test steps require at least one attempt.")

        final_execution = attempts[-1].execution

        if final_execution is None:
            raise ValueError("Executed usage-test steps must end with a successful attempt.")

        resolved_execution = execution if execution is not None else final_execution

        resolved_attempts = attempts

    return WorkflowStepRun(
        step_id=step_id,
        layer_index=0,
        status=WorkflowStepStatus.EXECUTED,
        execution=resolved_execution,
        attempts=resolved_attempts,
    )


def create_workflow_run(
    *,
    step_runs: tuple[WorkflowStepRun, ...],
) -> WorkflowRun:
    """Create deterministic workflow history for usage discovery."""

    context = Context()

    return WorkflowRun(
        workflow=WorkflowMetadata(
            id=FIRST_WORKFLOW_ID,
            name="Usage discovery workflow",
            description="Workflow used to test historical resource usage.",
            version="1.0.0",
        ),
        steps=step_runs,
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
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


def create_production_state(
    *,
    primary_model_identifier: str = MODEL_IDENTIFIER,
    substitute_model_identifiers: tuple[str, ...] = (SUBSTITUTE_MODEL_IDENTIFIER,),
) -> WorkflowProductionState:
    """Create deterministic production state with approved model substitutes."""

    workflow = create_fixed_prompt_workflow(
        model_identifier=primary_model_identifier,
    )

    substitutes = tuple(
        FixedModelSelection(
            provider=identifier.split(
                "/",
                maxsplit=1,
            )[0],
            model=identifier.split(
                "/",
                maxsplit=1,
            )[1],
        )
        for identifier in substitute_model_identifiers
    )

    return WorkflowProductionState(
        specification=workflow,
        model_substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=FIRST_STEP_ID,
                substitutes=substitutes,
            ),
        )
        if substitutes
        else (),
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


def test_production_model_usages_reports_primary_model() -> None:
    state = create_production_state()

    usages = production_model_usages(
        state,
        MODEL_IDENTIFIER,
    )

    assert len(usages) == 1
    assert usages[0].step_id == FIRST_STEP_ID
    assert usages[0].role is WorkflowProductionModelUsageRole.PRIMARY


def test_production_model_usages_reports_approved_substitute() -> None:
    state = create_production_state()

    usages = production_model_usages(
        state,
        SUBSTITUTE_MODEL_IDENTIFIER,
    )

    assert len(usages) == 1
    assert usages[0].step_id == FIRST_STEP_ID
    assert usages[0].role is WorkflowProductionModelUsageRole.SUBSTITUTE


def test_production_model_usages_preserves_multiple_matching_roles() -> None:
    workflow = WorkflowSpecification(
        metadata=create_metadata(
            workflow_id=FIRST_WORKFLOW_ID,
            name="Multi-step production workflow",
        ),
        steps=(
            WorkflowStepSpecification(
                id=FIRST_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=create_strategy_metadata(
                        strategy_id=FIRST_STRATEGY_ID,
                        name="First production prompt",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider="openrouter",
                        model="example-model",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=SECOND_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=create_strategy_metadata(
                        strategy_id=SECOND_STRATEGY_ID,
                        name="Second production prompt",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider="openrouter",
                        model="other-model",
                    ),
                ),
            ),
        ),
    )

    state = WorkflowProductionState(
        specification=workflow,
        model_substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=SECOND_STEP_ID,
                substitutes=(
                    FixedModelSelection(
                        provider="openrouter",
                        model="example-model",
                    ),
                ),
            ),
        ),
    )

    assert tuple(
        (usage.step_id, usage.role)
        for usage in production_model_usages(
            state,
            MODEL_IDENTIFIER,
        )
    ) == (
        (
            FIRST_STEP_ID,
            WorkflowProductionModelUsageRole.PRIMARY,
        ),
        (
            SECOND_STEP_ID,
            WorkflowProductionModelUsageRole.SUBSTITUTE,
        ),
    )


def test_production_model_usages_returns_empty_for_unused_model() -> None:
    state = create_production_state()

    assert (
        production_model_usages(
            state,
            OTHER_MODEL_IDENTIFIER,
        )
        == ()
    )


def test_production_uses_tool_when_active_specification_requires_capability() -> None:
    state = WorkflowProductionState(
        specification=create_tool_workflow(),
    )

    assert production_uses_tool(
        state,
        "word_count",
    )


def test_production_does_not_use_unconfigured_tool() -> None:
    state = WorkflowProductionState(
        specification=create_tool_workflow(),
    )

    assert not production_uses_tool(
        state,
        OTHER_TOOL_NAME,
    )


def test_prompt_only_production_does_not_use_tool() -> None:
    state = create_production_state()

    assert not production_uses_tool(
        state,
        "word_count",
    )


def test_historical_model_usages_reports_matching_execution() -> None:
    run = create_workflow_run(
        step_runs=(
            create_step_run(
                step_id=FIRST_STEP_ID,
                execution=create_execution_result(
                    resources=(
                        StrategyResourceBinding(
                            kind="model",
                            identifier=MODEL_IDENTIFIER,
                        ),
                    ),
                ),
            ),
        ),
    )

    usages = historical_model_usages(
        run,
        MODEL_IDENTIFIER,
    )

    assert len(usages) == 1
    assert usages[0].step_id == FIRST_STEP_ID
    assert usages[0].attempt_number == 1
    assert usages[0].identifier == MODEL_IDENTIFIER


def test_historical_model_usages_ignores_configured_but_unexecuted_model() -> None:
    run = create_workflow_run(
        step_runs=(
            create_step_run(
                step_id=FIRST_STEP_ID,
                execution=create_execution_result(
                    resources=(
                        StrategyResourceBinding(
                            kind="model",
                            identifier=OTHER_MODEL_IDENTIFIER,
                        ),
                    ),
                ),
            ),
        ),
    )

    assert (
        historical_model_usages(
            run,
            MODEL_IDENTIFIER,
        )
        == ()
    )


def test_historical_model_usages_preserves_matching_attempts() -> None:
    run = create_workflow_run(
        step_runs=(
            create_step_run(
                step_id=FIRST_STEP_ID,
                attempts=(
                    create_attempt(
                        attempt_number=1,
                        execution=create_execution_result(
                            resources=(
                                StrategyResourceBinding(
                                    kind="model",
                                    identifier=MODEL_IDENTIFIER,
                                ),
                            ),
                        ),
                    ),
                    create_attempt(
                        attempt_number=2,
                        execution=create_execution_result(
                            resources=(
                                StrategyResourceBinding(
                                    kind="model",
                                    identifier=MODEL_IDENTIFIER,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    assert tuple(
        usage.attempt_number
        for usage in historical_model_usages(
            run,
            MODEL_IDENTIFIER,
        )
    ) == (
        1,
        2,
    )
