"""Contract tests for production through the service API (ADR 0128)."""

from collections.abc import Iterator
from datetime import timedelta

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import WorkflowProductionRevision
from tests.api.test_runs import (
    COUNT_STEP_ID,
    COUNT_WORKFLOW_ID,
    MISSING_ID,
    stock,
    tool_step,
    workflow,
)
from tests.cli.test_production_inspection_commands import (
    CREATED_AT,
    FIRST_REVISION_ID,
    SECOND_REVISION_ID,
    STEP_ID,
    WORKFLOW_ID,
    create_state,
    create_workflow,
)

AUTHOR = "Eris Discordia <eris@example.com>"


@pytest.fixture
def stocked(
    instance: api.Azathoth,
) -> api.Azathoth:
    """Return an instance holding the word count workflow, not yet in production."""

    stock(instance)

    return instance


@pytest.fixture
def authored(
    location: str,
) -> Iterator[api.Azathoth]:
    """Return an instance over the same database that records the test author."""

    with api.open(location, author=AUTHOR) as opened:
        stock(opened)

        yield opened


def revise_count(
    instance: api.Azathoth,
) -> None:
    """Import a second revision of the word count workflow, with another message."""

    instance.workflows.import_document(
        workflow(
            COUNT_WORKFLOW_ID,
            tool_step(COUNT_STEP_ID, "word_count", message="Counting again"),
        )
    )


def save_prompt_history(
    location: str,
) -> None:
    """Save two revisions of an OpenRouter-pinned workflow in production, the second active."""

    repositories = open_repositories(location)

    repositories.production_revisions.save(
        WorkflowProductionRevision(
            id=FIRST_REVISION_ID,
            state=create_state("first-model"),
            created_at=CREATED_AT,
        )
    )
    repositories.production_revisions.save(
        WorkflowProductionRevision(
            id=SECOND_REVISION_ID,
            state=create_state("second-model"),
            created_at=CREATED_AT + timedelta(minutes=5),
        )
    )
    repositories.production_states.set(create_state("second-model"))


# Reading production


def test_a_configured_workflow_not_in_production_has_no_state(
    stocked: api.Azathoth,
) -> None:
    assert stocked.production.get(COUNT_WORKFLOW_ID) is None
    assert stocked.production.revisions(COUNT_WORKFLOW_ID) == ()


def test_an_unknown_workflow_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError):
        instance.production.get(MISSING_ID)

    with pytest.raises(api.NotFoundError):
        instance.production.revisions(MISSING_ID)


def test_revisions_refuse_a_limit_below_one(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError, match=api.LIMIT_MESSAGE):
        stocked.production.revisions(COUNT_WORKFLOW_ID, limit=0)


def test_production_names_each_prompt_steps_models(
    instance: api.Azathoth,
    location: str,
) -> None:
    save_prompt_history(location)

    state = instance.production.get(WORKFLOW_ID)

    assert state is not None
    assert state.revision is not None
    assert state.revision.revision_id == SECOND_REVISION_ID
    assert state.steps == (
        api.ProductionStepModels(
            step_id=STEP_ID,
            primary="openrouter/second-model",
            substitutes=(),
        ),
    )
    assert state.command == f"azathoth workflow production {WORKFLOW_ID}"


def test_revisions_are_newest_first_with_the_active_one_marked(
    instance: api.Azathoth,
    location: str,
) -> None:
    save_prompt_history(location)

    revisions = instance.production.revisions(WORKFLOW_ID)

    assert [revision.revision_id for revision in revisions] == [
        SECOND_REVISION_ID,
        FIRST_REVISION_ID,
    ]
    assert [revision.active for revision in revisions] == [True, False]
    assert revisions[1].author is None
    assert revisions[1].restores is None
    assert [
        revision.revision_id for revision in instance.production.revisions(WORKFLOW_ID, limit=1)
    ] == [SECOND_REVISION_ID]


# Promoting


def test_a_promotion_is_active_and_records_its_author(
    authored: api.Azathoth,
) -> None:
    promoted = authored.production.promote(COUNT_WORKFLOW_ID)

    assert promoted.active
    assert promoted.workflow_id == COUNT_WORKFLOW_ID
    assert promoted.workflow_revision == 1
    assert promoted.author == api.Author(name="Eris Discordia", email="eris@example.com")
    assert promoted.restores is None
    assert promoted.steps == ()

    state = authored.production.get(COUNT_WORKFLOW_ID)

    assert state is not None
    assert state.revision == promoted
    assert state.workflow_revision == 1


def test_a_promoted_workflow_can_be_invoked(
    stocked: api.Azathoth,
) -> None:
    stocked.production.promote(COUNT_WORKFLOW_ID)

    outcome = stocked.runs.invoke(COUNT_WORKFLOW_ID, input="one two three")

    assert outcome.status == "succeeded"
    assert outcome.result == {"result": 3}


def test_an_unconfigured_workflow_cannot_be_promoted(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Workflow {MISSING_ID} is not configured."):
        instance.production.promote(MISSING_ID)


def test_a_workflow_without_a_result_cannot_be_promoted(
    instance: api.Azathoth,
    location: str,
) -> None:
    open_repositories(location).workflows.save(create_workflow())

    with pytest.raises(api.WorkflowResultMissingError) as raised:
        instance.production.promote(WORKFLOW_ID)

    assert str(raised.value) == f"Workflow {WORKFLOW_ID} does not declare a result."
    assert open_repositories(location).production_states.get(WORKFLOW_ID) is None


def test_promoting_a_missing_experiments_winner_is_refused(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.ExperimentNotFoundError) as raised:
        stocked.production.promote(COUNT_WORKFLOW_ID, experiment_id=MISSING_ID)

    assert isinstance(raised.value, api.NotFoundError)
    assert str(raised.value) == f"Experiment {MISSING_ID} was not found."
    assert stocked.production.get(COUNT_WORKFLOW_ID) is None


# Rolling back


def test_a_rollback_restores_the_previous_promotion(
    authored: api.Azathoth,
) -> None:
    first = authored.production.promote(COUNT_WORKFLOW_ID)

    revise_count(authored)
    second = authored.production.promote(COUNT_WORKFLOW_ID)

    restored = authored.production.roll_back(COUNT_WORKFLOW_ID)

    assert second.workflow_revision == 2
    assert restored.restores == first.revision_id
    assert restored.workflow_revision == 1
    assert restored.active
    assert restored.author is not None

    state = authored.production.get(COUNT_WORKFLOW_ID)

    assert state is not None
    assert state.revision == restored
    assert [revision.active for revision in authored.production.revisions(COUNT_WORKFLOW_ID)] == [
        True,
        False,
        False,
    ]


def test_a_rollback_to_a_named_revision(
    stocked: api.Azathoth,
) -> None:
    first = stocked.production.promote(COUNT_WORKFLOW_ID)

    revise_count(stocked)
    stocked.production.promote(COUNT_WORKFLOW_ID)

    assert stocked.production.roll_back(COUNT_WORKFLOW_ID, to=first.revision_id).restores == (
        first.revision_id
    )


def test_a_rollback_with_nothing_earlier_is_a_conflict(
    stocked: api.Azathoth,
) -> None:
    stocked.production.promote(COUNT_WORKFLOW_ID)

    with pytest.raises(api.NothingToRollBackToError) as raised:
        stocked.production.roll_back(COUNT_WORKFLOW_ID)

    assert isinstance(raised.value, api.ConflictError)
    assert str(raised.value) == (
        f"Workflow {COUNT_WORKFLOW_ID} has no earlier production revision to roll back to."
    )


def test_a_workflow_not_in_production_has_nothing_to_roll_back_to(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.NothingToRollBackToError, match="is not in production"):
        stocked.production.roll_back(COUNT_WORKFLOW_ID)


def test_an_unknown_workflow_cannot_be_rolled_back(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError):
        instance.production.roll_back(MISSING_ID)


def test_a_rollback_to_a_revision_the_workflow_never_had_is_not_found(
    stocked: api.Azathoth,
) -> None:
    first = stocked.production.promote(COUNT_WORKFLOW_ID)

    with pytest.raises(api.NotFoundError) as raised:
        stocked.production.roll_back(COUNT_WORKFLOW_ID, to=MISSING_ID)

    state = stocked.production.get(COUNT_WORKFLOW_ID)

    assert str(raised.value) == (
        f"Workflow {COUNT_WORKFLOW_ID} has no production revision {MISSING_ID}."
    )
    assert state is not None
    assert state.revision == first


def test_a_rollback_to_a_model_no_longer_authorized_is_refused(
    instance: api.Azathoth,
    location: str,
) -> None:
    save_prompt_history(location)

    with pytest.raises(api.ModelNotAuthorizedError) as raised:
        instance.production.roll_back(WORKFLOW_ID)

    assert isinstance(raised.value, api.ConflictError)
    assert "openrouter/first-model, which the portfolio no longer authorizes" in str(raised.value)

    state = instance.production.get(WORKFLOW_ID)

    assert state is not None
    assert state.revision is not None
    assert state.revision.revision_id == SECOND_REVISION_ID


def test_production_values_are_their_own_json(
    stocked: api.Azathoth,
) -> None:
    promoted = stocked.production.promote(COUNT_WORKFLOW_ID)
    state = stocked.production.get(COUNT_WORKFLOW_ID)

    assert state is not None
    assert api.ProductionRevisionSummary.model_validate_json(promoted.model_dump_json()) == promoted
    assert api.ProductionState.model_validate_json(state.model_dump_json()) == state


def test_a_closed_instance_refuses_production_calls(
    location: str,
) -> None:
    instance = api.open(location)
    instance.close()

    with pytest.raises(api.InstanceClosedError):
        instance.production.get(COUNT_WORKFLOW_ID)
