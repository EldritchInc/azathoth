"""Tests for SQLite workflow production-state persistence."""

from pathlib import Path
from uuid import UUID

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowProductionStateRepository,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")


def create_state(
    *,
    workflow_id: UUID = FIRST_WORKFLOW_ID,
    step_id: UUID = FIRST_STEP_ID,
    strategy_id: UUID = FIRST_STRATEGY_ID,
    model: str = "production-model",
) -> WorkflowProductionState:
    """Create deterministic workflow production state."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name=f"production-{workflow_id}",
                description="Exercise SQLite production-state persistence.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=step_id,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=strategy_id,
                            name="production-prompt",
                            description="Exercise SQLite production persistence.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Return success.",
                        ),
                        model_selection=FixedModelSelection(
                            provider="test-provider",
                            model=model,
                        ),
                    ),
                ),
            ),
        )
    )


def test_sqlite_production_repository_starts_empty(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowProductionStateRepository(
        tmp_path / "production.db",
    )

    assert repository.states() == ()
    assert repository.get(FIRST_WORKFLOW_ID) is None


def test_sqlite_production_repository_sets_state(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowProductionStateRepository(
        tmp_path / "production.db",
    )

    state = create_state()

    repository.set(state)

    assert repository.get(FIRST_WORKFLOW_ID) == state
    assert repository.states() == (state,)


def test_sqlite_production_repository_replaces_active_state(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowProductionStateRepository(
        tmp_path / "production.db",
    )

    initial = create_state(
        model="primary",
    )

    replacement = create_state(
        model="replacement",
    )

    repository.set(initial)
    repository.set(replacement)

    assert repository.get(FIRST_WORKFLOW_ID) == replacement
    assert repository.states() == (replacement,)


def test_sqlite_production_repository_preserves_order_when_replacing(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowProductionStateRepository(
        tmp_path / "production.db",
    )

    first = create_state(
        workflow_id=FIRST_WORKFLOW_ID,
        step_id=FIRST_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
        model="primary",
    )

    second = create_state(
        workflow_id=SECOND_WORKFLOW_ID,
        step_id=SECOND_STEP_ID,
        strategy_id=SECOND_STRATEGY_ID,
    )

    replacement = create_state(
        workflow_id=FIRST_WORKFLOW_ID,
        step_id=FIRST_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
        model="replacement",
    )

    repository.set(first)
    repository.set(second)
    repository.set(replacement)

    assert repository.states() == (
        replacement,
        second,
    )


def test_sqlite_production_repository_survives_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    state = create_state(
        model="production-model",
    )

    SQLiteWorkflowProductionStateRepository(
        database,
    ).set(
        state,
    )

    reconstructed = SQLiteWorkflowProductionStateRepository(
        database,
    ).get(
        FIRST_WORKFLOW_ID,
    )

    assert reconstructed == state


def test_sqlite_production_repository_preserves_fixed_selection_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    state = create_state(
        model="production-model",
    )

    SQLiteWorkflowProductionStateRepository(
        database,
    ).set(
        state,
    )

    restored = SQLiteWorkflowProductionStateRepository(
        database,
    ).get(
        FIRST_WORKFLOW_ID,
    )

    assert restored is not None

    specification = restored.specification.steps[0].specification

    assert isinstance(
        specification,
        PromptStrategySpec,
    )

    assert isinstance(
        specification.model_selection,
        FixedModelSelection,
    )

    assert specification.model_selection.identifier == ("test-provider/production-model")
