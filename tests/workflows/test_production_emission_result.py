"""Tests for caller-visible production workflow emission."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    ProductionEmissionError,
    WorkflowMetadata,
    WorkflowProductionEmission,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValue,
    WorkflowValueBinding,
    WorkflowValueReference,
    emit_production_result,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

REVISION_ID = UUID("55555555-5555-5555-5555-555555555555")

RECORDED_AT = datetime(
    2026,
    9,
    3,
    16,
    0,
    tzinfo=UTC,
)


def create_revision(
    *,
    emissions: tuple[
        WorkflowProductionEmission,
        ...,
    ],
) -> WorkflowProductionRevision:
    """Create deterministic production revision."""

    return WorkflowProductionRevision(
        id=REVISION_ID,
        state=WorkflowProductionState(
            specification=WorkflowSpecification(
                metadata=WorkflowMetadata(
                    id=WORKFLOW_ID,
                    name="production-emission",
                    description="Exercise safe production emission.",
                    version="1.0.0",
                ),
                steps=(
                    WorkflowStepSpecification(
                        id=STEP_ID,
                        specification=PromptStrategySpec(
                            metadata=StrategyMetadata(
                                id=STRATEGY_ID,
                                name="classify",
                                description="Classify production input.",
                                version="1.0.0",
                            ),
                            prompt=Prompt(
                                text="Classify.",
                            ),
                            model_selection=FixedModelSelection(
                                provider="test-provider",
                                model="production-model",
                            ),
                        ),
                        outputs=(
                            WorkflowValueBinding(
                                name="classification",
                            ),
                            WorkflowValueBinding(
                                name="internal_analysis",
                            ),
                        ),
                    ),
                ),
            ),
            emissions=emissions,
        ),
    )


def test_empty_emission_policy_returns_empty_result() -> None:
    revision = create_revision(
        emissions=(),
    )

    run = create_run(
        values=(
            WorkflowValue(
                name="classification",
                value="positive",
                producer_step_id=STEP_ID,
            ),
        ),
    )

    assert (
        emit_production_result(
            revision=revision,
            run=run,
        )
        == {}
    )


def test_emission_returns_only_explicit_value() -> None:
    create_revision(
        emissions=(
            WorkflowProductionEmission(
                name="label",
                source=WorkflowValueReference(
                    producer_step_id=STEP_ID,
                    name="classification",
                ),
            ),
        ),
    )


def create_run(
    *,
    values: tuple[
        WorkflowValue,
        ...,
    ],
) -> WorkflowRun:
    """Create deterministic successful workflow run."""

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="classify",
        strategy_version="1.0.0",
        output={
            "result": "success",
        },
        initial_context=Context(),
        final_context=Context(),
        started_at=RECORDED_AT,
        completed_at=RECORDED_AT,
    )

    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=RECORDED_AT,
        completed_at=RECORDED_AT,
        execution=execution,
    )

    return WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="production-emission",
            description="Exercise safe production emission.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=execution,
                attempts=(attempt,),
                values=values,
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=RECORDED_AT,
        completed_at=RECORDED_AT,
    )


def test_emission_uses_exact_producer_step() -> None:
    revision = create_revision(
        emissions=(
            WorkflowProductionEmission(
                name="label",
                source=WorkflowValueReference(
                    producer_step_id=STEP_ID,
                    name="classification",
                ),
            ),
        ),
    )

    run = create_run(
        values=(
            WorkflowValue(
                name="classification",
                value="selected",
                producer_step_id=STEP_ID,
            ),
            WorkflowValue(
                name="classification",
                value="wrong producer",
                producer_step_id=SECOND_STEP_ID,
            ),
        ),
    )

    assert emit_production_result(
        revision=revision,
        run=run,
    ) == {
        "label": "selected",
    }


def test_emission_renames_internal_value() -> None:
    revision = create_revision(
        emissions=(
            WorkflowProductionEmission(
                name="public_label",
                source=WorkflowValueReference(
                    producer_step_id=STEP_ID,
                    name="classification",
                ),
            ),
        ),
    )

    run = create_run(
        values=(
            WorkflowValue(
                name="classification",
                value="positive",
                producer_step_id=STEP_ID,
            ),
        ),
    )

    assert emit_production_result(
        revision=revision,
        run=run,
    ) == {
        "public_label": "positive",
    }


def test_missing_declared_emission_fails() -> None:
    revision = create_revision(
        emissions=(
            WorkflowProductionEmission(
                name="label",
                source=WorkflowValueReference(
                    producer_step_id=STEP_ID,
                    name="classification",
                ),
            ),
        ),
    )

    run = create_run(
        values=(),
    )

    with pytest.raises(
        ProductionEmissionError,
        match="was not produced uniquely",
    ):
        emit_production_result(
            revision=revision,
            run=run,
        )
