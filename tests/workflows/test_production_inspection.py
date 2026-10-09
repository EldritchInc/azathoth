"""Tests for identifying the revision behind active production state."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    active_production_revision,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

FIRST_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")

SECOND_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")

THIRD_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3")

CREATED_AT = datetime(
    2026,
    10,
    9,
    17,
    0,
    tzinfo=UTC,
)


def create_state(
    *,
    model: str,
    workflow_id: UUID = WORKFLOW_ID,
) -> WorkflowProductionState:
    """Create production state pinning one prompt step to one model."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name="deployed workflow",
                description="Workflow used to test production inspection.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="Deployed prompt",
                            description="Deployed prompt description.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Return exactly OK.",
                        ),
                        model_selection=FixedModelSelection(
                            provider="openrouter",
                            model=model,
                        ),
                    ),
                ),
            ),
        ),
    )


def create_revision(
    revision_id: UUID,
    state: WorkflowProductionState,
    *,
    created_at: datetime,
) -> WorkflowProductionRevision:
    """Create one deterministic production revision."""

    return WorkflowProductionRevision(
        id=revision_id,
        state=state,
        created_at=created_at,
    )


def test_returns_revision_that_deployed_active_state() -> None:
    first = create_state(model="first-model")
    second = create_state(model="second-model")

    revision = active_production_revision(
        second,
        (
            create_revision(
                FIRST_REVISION_ID,
                first,
                created_at=CREATED_AT,
            ),
            create_revision(
                SECOND_REVISION_ID,
                second,
                created_at=CREATED_AT + timedelta(minutes=5),
            ),
        ),
    )

    assert revision is not None
    assert revision.id == SECOND_REVISION_ID


def test_returns_newest_of_identical_deployments() -> None:
    first = create_state(model="first-model")
    second = create_state(model="second-model")

    revision = active_production_revision(
        first,
        (
            create_revision(
                FIRST_REVISION_ID,
                first,
                created_at=CREATED_AT,
            ),
            create_revision(
                SECOND_REVISION_ID,
                second,
                created_at=CREATED_AT + timedelta(minutes=5),
            ),
            create_revision(
                THIRD_REVISION_ID,
                first,
                created_at=CREATED_AT + timedelta(minutes=10),
            ),
        ),
    )

    assert revision is not None
    assert revision.id == THIRD_REVISION_ID


def test_does_not_depend_on_revision_order() -> None:
    state = create_state(model="first-model")

    revision = active_production_revision(
        state,
        (
            create_revision(
                SECOND_REVISION_ID,
                state,
                created_at=CREATED_AT + timedelta(minutes=5),
            ),
            create_revision(
                FIRST_REVISION_ID,
                state,
                created_at=CREATED_AT,
            ),
        ),
    )

    assert revision is not None
    assert revision.id == SECOND_REVISION_ID


def test_later_revision_wins_timestamp_tie() -> None:
    state = create_state(model="first-model")

    revision = active_production_revision(
        state,
        (
            create_revision(
                FIRST_REVISION_ID,
                state,
                created_at=CREATED_AT,
            ),
            create_revision(
                SECOND_REVISION_ID,
                state,
                created_at=CREATED_AT,
            ),
        ),
    )

    assert revision is not None
    assert revision.id == SECOND_REVISION_ID


def test_ignores_revisions_of_other_workflows() -> None:
    state = create_state(model="first-model")

    revision = active_production_revision(
        state,
        (
            create_revision(
                FIRST_REVISION_ID,
                create_state(
                    model="first-model",
                    workflow_id=OTHER_WORKFLOW_ID,
                ),
                created_at=CREATED_AT,
            ),
        ),
    )

    assert revision is None


def test_returns_none_when_active_state_was_never_recorded() -> None:
    revision = active_production_revision(
        create_state(model="unrecorded-model"),
        (
            create_revision(
                FIRST_REVISION_ID,
                create_state(model="first-model"),
                created_at=CREATED_AT,
            ),
        ),
    )

    assert revision is None


def test_returns_none_without_revisions() -> None:
    assert active_production_revision(create_state(model="first-model"), ()) is None
