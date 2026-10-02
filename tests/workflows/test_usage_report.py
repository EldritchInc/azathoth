"""Tests for aggregated workflow model usage reports."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.prompting import (
    FixedModelSelection,
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import (
    StrategyMetadata,
    StrategyResourceBinding,
)
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowModelUsageEntry,
    WorkflowModelUsageReport,
    WorkflowProductionModelSubstitution,
    WorkflowProductionModelUsageRole,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    model_usage_report,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

THIRD_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

FIRST_RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

SECOND_RUN_ID = UUID("99999999-9999-4999-8999-999999999992")

THIRD_RUN_ID = UUID("99999999-9999-4999-8999-999999999993")

MODEL_IDENTIFIER = "openrouter/example-model"
OTHER_MODEL_IDENTIFIER = "openrouter/other-model"
SUBSTITUTE_MODEL_IDENTIFIER = "openrouter/substitute-model"

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    tzinfo=UTC,
)


def create_metadata(
    workflow_id: UUID,
) -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=workflow_id,
        name=f"Workflow {workflow_id}",
        description="Workflow used to test model usage reports.",
        version="1.0.0",
    )


def create_model_selection(
    identifier: str,
) -> FixedModelSelection:
    """Create one fixed model selection from a provider-qualified identifier."""

    provider, model = identifier.split(
        "/",
        maxsplit=1,
    )

    return FixedModelSelection(
        provider=provider,
        model=model,
    )


def create_fixed_workflow(
    workflow_id: UUID,
    *,
    model_identifier: str = MODEL_IDENTIFIER,
) -> WorkflowSpecification:
    """Create a one-step workflow configured to one exact model."""

    return WorkflowSpecification(
        metadata=create_metadata(workflow_id),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Fixed prompt",
                        description="Fixed prompt description.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=create_model_selection(model_identifier),
                ),
            ),
        ),
    )


def create_portfolio_workflow(
    workflow_id: UUID,
) -> WorkflowSpecification:
    """Create a one-step workflow selecting from the authorized portfolio."""

    return WorkflowSpecification(
        metadata=create_metadata(workflow_id),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Portfolio prompt",
                        description="Portfolio prompt description.",
                        version="1.0.0",
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


def create_production_state(
    workflow_id: UUID,
    *,
    primary_model_identifier: str = MODEL_IDENTIFIER,
    substitute_model_identifiers: tuple[str, ...] = (),
) -> WorkflowProductionState:
    """Create active production state with optional approved substitutes."""

    substitutes = tuple(
        create_model_selection(identifier) for identifier in substitute_model_identifiers
    )

    return WorkflowProductionState(
        specification=create_fixed_workflow(
            workflow_id,
            model_identifier=primary_model_identifier,
        ),
        model_substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=STEP_ID,
                substitutes=substitutes,
            ),
        )
        if substitutes
        else (),
    )


def create_run(
    workflow_id: UUID,
    *,
    run_id: UUID,
    executed_model_identifier: str = MODEL_IDENTIFIER,
    started_at: datetime = STARTED_AT,
) -> WorkflowRun:
    """Create one workflow run whose single step executed one model."""

    context = Context()
    completed_at = started_at + timedelta(seconds=1)

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="Fixed prompt",
        strategy_version="1.0.0",
        output="OK",
        resources=(
            StrategyResourceBinding(
                kind="model",
                identifier=executed_model_identifier,
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )

    return WorkflowRun(
        id=run_id,
        workflow=create_metadata(workflow_id),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=execution,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution=execution,
                    ),
                ),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )


def test_report_is_empty_when_nothing_uses_model() -> None:
    report = model_usage_report(
        MODEL_IDENTIFIER,
        specifications=(
            create_fixed_workflow(
                FIRST_WORKFLOW_ID,
                model_identifier=OTHER_MODEL_IDENTIFIER,
            ),
            create_portfolio_workflow(SECOND_WORKFLOW_ID),
        ),
        production_states=(
            create_production_state(
                THIRD_WORKFLOW_ID,
                primary_model_identifier=OTHER_MODEL_IDENTIFIER,
            ),
        ),
        runs=(
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
                executed_model_identifier=OTHER_MODEL_IDENTIFIER,
            ),
        ),
    )

    assert report.identifier == MODEL_IDENTIFIER
    assert report.workflows == ()
    assert not report.used
    assert not report.in_production
    assert report.production_workflows == ()


def test_report_records_configured_workflow() -> None:
    report = model_usage_report(
        MODEL_IDENTIFIER,
        specifications=(create_fixed_workflow(FIRST_WORKFLOW_ID),),
        production_states=(),
        runs=(),
    )

    assert report.used
    assert not report.in_production
    assert len(report.workflows) == 1

    entry = report.workflows[0]

    assert entry.workflow.id == FIRST_WORKFLOW_ID
    assert entry.configured
    assert entry.production == ()
    assert entry.runs == ()
    assert not entry.in_production


def test_report_records_production_roles() -> None:
    report = model_usage_report(
        SUBSTITUTE_MODEL_IDENTIFIER,
        specifications=(create_fixed_workflow(FIRST_WORKFLOW_ID),),
        production_states=(
            create_production_state(
                FIRST_WORKFLOW_ID,
                substitute_model_identifiers=(SUBSTITUTE_MODEL_IDENTIFIER,),
            ),
        ),
        runs=(),
    )

    assert report.in_production
    assert len(report.workflows) == 1

    entry = report.workflows[0]

    assert not entry.configured
    assert entry.in_production
    assert tuple((usage.step_id, usage.role) for usage in entry.production) == (
        (
            STEP_ID,
            WorkflowProductionModelUsageRole.SUBSTITUTE,
        ),
    )


def test_report_merges_configured_production_and_history_per_workflow() -> None:
    report = model_usage_report(
        MODEL_IDENTIFIER,
        specifications=(create_fixed_workflow(FIRST_WORKFLOW_ID),),
        production_states=(create_production_state(FIRST_WORKFLOW_ID),),
        runs=(
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
            ),
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=SECOND_RUN_ID,
                executed_model_identifier=OTHER_MODEL_IDENTIFIER,
            ),
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=THIRD_RUN_ID,
                started_at=STARTED_AT + timedelta(minutes=5),
            ),
        ),
    )

    assert len(report.workflows) == 1

    entry = report.workflows[0]

    assert entry.configured
    assert tuple(usage.role for usage in entry.production) == (
        WorkflowProductionModelUsageRole.PRIMARY,
    )
    assert tuple(run.run_id for run in entry.runs) == (
        FIRST_RUN_ID,
        THIRD_RUN_ID,
    )
    assert entry.runs[1].started_at == STARTED_AT + timedelta(minutes=5)
    assert entry.runs[0].usages[0].step_id == STEP_ID
    assert entry.runs[0].usages[0].identifier == MODEL_IDENTIFIER


def test_report_preserves_workflows_no_longer_configured() -> None:
    report = model_usage_report(
        MODEL_IDENTIFIER,
        specifications=(),
        production_states=(create_production_state(FIRST_WORKFLOW_ID),),
        runs=(
            create_run(
                SECOND_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
            ),
        ),
    )

    assert tuple(
        (
            entry.workflow.id,
            entry.configured,
            entry.in_production,
            len(entry.runs),
        )
        for entry in report.workflows
    ) == (
        (FIRST_WORKFLOW_ID, False, True, 0),
        (SECOND_WORKFLOW_ID, False, False, 1),
    )


def test_report_orders_workflows_by_discovery_source() -> None:
    report = model_usage_report(
        MODEL_IDENTIFIER,
        specifications=(
            create_fixed_workflow(SECOND_WORKFLOW_ID),
            create_fixed_workflow(FIRST_WORKFLOW_ID),
        ),
        production_states=(create_production_state(THIRD_WORKFLOW_ID),),
        runs=(
            create_run(
                FIRST_WORKFLOW_ID,
                run_id=FIRST_RUN_ID,
            ),
        ),
    )

    assert tuple(entry.workflow.id for entry in report.workflows) == (
        SECOND_WORKFLOW_ID,
        FIRST_WORKFLOW_ID,
        THIRD_WORKFLOW_ID,
    )


def test_report_lists_only_production_workflows() -> None:
    report = model_usage_report(
        MODEL_IDENTIFIER,
        specifications=(
            create_fixed_workflow(FIRST_WORKFLOW_ID),
            create_fixed_workflow(SECOND_WORKFLOW_ID),
        ),
        production_states=(create_production_state(SECOND_WORKFLOW_ID),),
        runs=(),
    )

    assert tuple(entry.workflow.id for entry in report.production_workflows) == (
        SECOND_WORKFLOW_ID,
    )


def test_usage_entry_requires_at_least_one_usage() -> None:
    with pytest.raises(ValidationError):
        WorkflowModelUsageEntry(
            workflow=create_metadata(FIRST_WORKFLOW_ID),
        )


def test_report_rejects_duplicate_workflows() -> None:
    entry = WorkflowModelUsageEntry(
        workflow=create_metadata(FIRST_WORKFLOW_ID),
        configured=True,
    )

    with pytest.raises(ValidationError):
        WorkflowModelUsageReport(
            identifier=MODEL_IDENTIFIER,
            workflows=(
                entry,
                entry,
            ),
        )
