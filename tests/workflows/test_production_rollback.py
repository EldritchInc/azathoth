"""Tests for rolling a workflow's production back to an earlier revision (ADR 0128)."""

from datetime import timedelta
from uuid import UUID

import pytest

from azathoth.prompting import FixedModelSelection
from azathoth.revisions import Author
from azathoth.workflows import (
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    NothingToRollBackToError,
    ProductionRevisionNotFoundError,
    RollbackModelNotAuthorizedError,
    WorkflowNotInProductionError,
    WorkflowProductionModelSubstitution,
    WorkflowProductionRevision,
    WorkflowProductionState,
    roll_back_workflow_production,
)
from tests.cli.test_production_inspection_commands import (
    CREATED_AT,
    FIRST_REVISION_ID,
    OTHER_REVISION_ID,
    OTHER_WORKFLOW_ID,
    SECOND_REVISION_ID,
    STEP_ID,
    THIRD_REVISION_ID,
    WORKFLOW_ID,
    create_state,
)

AUTHOR = Author(name="Eris Discordia", email="eris@example.com")

UNKNOWN_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9")

BACKUP = FixedModelSelection(provider="openrouter", model="backup-model")


class Production:
    """One workflow's production history, in memory, with the models still authorized."""

    def __init__(
        self,
        *,
        authorized: tuple[str, ...] = (
            "openrouter/first-model",
            "openrouter/second-model",
            "openrouter/third-model",
        ),
    ) -> None:
        self.states = InMemoryWorkflowProductionStateRepository()
        self.revisions = InMemoryWorkflowProductionRevisionRepository()
        self.authorized = set(authorized)

    def deploy(
        self,
        revision_id: UUID,
        state: WorkflowProductionState,
        *,
        minutes: int,
        active: bool = False,
    ) -> WorkflowProductionRevision:
        """Save one revision made some minutes after the start, and make it active if asked."""

        revision = WorkflowProductionRevision(
            id=revision_id,
            state=state,
            created_at=CREATED_AT + timedelta(minutes=minutes),
        )

        self.revisions.save(revision)

        if active:
            self.states.set(state)

        return revision

    def roll_back(
        self,
        *,
        to: UUID | None = None,
    ) -> WorkflowProductionRevision:
        """Roll the workflow back, as the test author."""

        return roll_back_workflow_production(
            workflow_id=WORKFLOW_ID,
            repository=self.states,
            revision_repository=self.revisions,
            authorized=lambda identifier: identifier in self.authorized,
            to=to,
            author=AUTHOR,
        )


def two_promotions(
    production: Production,
) -> tuple[WorkflowProductionRevision, WorkflowProductionRevision]:
    """Promote the first model, then the second, which is active."""

    first = production.deploy(FIRST_REVISION_ID, create_state("first-model"), minutes=0)
    second = production.deploy(
        SECOND_REVISION_ID, create_state("second-model"), minutes=5, active=True
    )

    return first, second


def test_a_rollback_restores_the_revision_before_the_active_one() -> None:
    production = Production()
    first, _second = two_promotions(production)

    restored = production.roll_back()

    assert restored.state == first.state
    assert restored.restores == FIRST_REVISION_ID
    assert restored.author == AUTHOR
    assert restored.id not in (FIRST_REVISION_ID, SECOND_REVISION_ID)
    assert production.states.get(WORKFLOW_ID) == first.state
    assert production.revisions.get(restored.id) == restored
    assert len(production.revisions.revisions_for_workflow(WORKFLOW_ID)) == 3


def test_a_rollback_looks_before_the_active_revision_not_the_newest() -> None:
    production = Production()

    production.deploy(FIRST_REVISION_ID, create_state("first-model"), minutes=0)
    production.deploy(SECOND_REVISION_ID, create_state("second-model"), minutes=5, active=True)
    production.deploy(THIRD_REVISION_ID, create_state("third-model"), minutes=10)

    assert production.roll_back().restores == FIRST_REVISION_ID


def test_rolling_back_again_undoes_the_rollback() -> None:
    production = Production()
    _first, second = two_promotions(production)

    production.roll_back()
    undone = production.roll_back()

    assert undone.restores == SECOND_REVISION_ID
    assert production.states.get(WORKFLOW_ID) == second.state


def test_a_rollback_restores_the_revision_it_is_told_to() -> None:
    production = Production()

    two_promotions(production)
    third = production.deploy(THIRD_REVISION_ID, create_state("third-model"), minutes=10)

    restored = production.roll_back(to=THIRD_REVISION_ID)

    assert restored.restores == THIRD_REVISION_ID
    assert production.states.get(WORKFLOW_ID) == third.state


def test_a_rollback_with_nothing_earlier_is_refused() -> None:
    production = Production()

    production.deploy(FIRST_REVISION_ID, create_state("first-model"), minutes=0, active=True)

    with pytest.raises(NothingToRollBackToError) as raised:
        production.roll_back()

    assert str(raised.value) == (
        f"Workflow {WORKFLOW_ID} has no earlier production revision to roll back to."
    )
    assert len(production.revisions.revisions_for_workflow(WORKFLOW_ID)) == 1


def test_a_workflow_not_in_production_has_nothing_to_roll_back_to() -> None:
    production = Production()

    production.deploy(FIRST_REVISION_ID, create_state("first-model"), minutes=0)

    with pytest.raises(WorkflowNotInProductionError) as raised:
        production.roll_back()

    assert isinstance(raised.value, NothingToRollBackToError)
    assert str(raised.value) == f"Workflow {WORKFLOW_ID} is not in production."


@pytest.mark.parametrize("revision_id", (UNKNOWN_REVISION_ID, OTHER_REVISION_ID))
def test_a_rollback_to_a_revision_this_workflow_never_had_is_refused(
    revision_id: UUID,
) -> None:
    production = Production()

    two_promotions(production)
    production.deploy(OTHER_REVISION_ID, create_state(workflow_id=OTHER_WORKFLOW_ID), minutes=0)

    with pytest.raises(ProductionRevisionNotFoundError) as raised:
        production.roll_back(to=revision_id)

    assert str(raised.value) == (
        f"Workflow {WORKFLOW_ID} has no production revision {revision_id}."
    )


def test_a_rollback_to_the_active_revision_is_refused() -> None:
    production = Production()

    two_promotions(production)

    with pytest.raises(NothingToRollBackToError) as raised:
        production.roll_back(to=SECOND_REVISION_ID)

    assert str(raised.value) == (
        f"Production revision {SECOND_REVISION_ID} is already active for workflow {WORKFLOW_ID}."
    )


def test_a_rollback_to_a_model_no_longer_authorized_is_refused_and_changes_nothing() -> None:
    production = Production(authorized=("openrouter/second-model",))
    _first, second = two_promotions(production)

    with pytest.raises(RollbackModelNotAuthorizedError) as raised:
        production.roll_back()

    assert str(raised.value) == (
        f"Step {STEP_ID} of production revision {FIRST_REVISION_ID} uses "
        "openrouter/first-model, which the portfolio no longer authorizes; "
        "authorize it again before rolling back to it."
    )
    assert production.states.get(WORKFLOW_ID) == second.state
    assert len(production.revisions.revisions_for_workflow(WORKFLOW_ID)) == 2


def test_a_rollback_may_rely_on_an_approved_substitute() -> None:
    production = Production(authorized=("openrouter/second-model", BACKUP.identifier))
    substituted = create_state("first-model").model_copy(
        update={
            "model_substitutions": (
                WorkflowProductionModelSubstitution(step_id=STEP_ID, substitutes=(BACKUP,)),
            )
        }
    )

    production.deploy(FIRST_REVISION_ID, substituted, minutes=0)
    production.deploy(SECOND_REVISION_ID, create_state("second-model"), minutes=5, active=True)

    assert production.roll_back().state == substituted
