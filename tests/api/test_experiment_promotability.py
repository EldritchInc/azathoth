"""Contract tests for whether an experiment's winner can still be promoted (ADR 0131)."""

import shlex
from uuid import UUID

import pytest

from azathoth import api
from azathoth.cli.parsing import build_parser
from tests.api.test_benchmark_run import counted
from tests.api.test_experiment_comparison import stocked
from tests.api.test_runs import COUNT_STEP_ID, COUNT_WORKFLOW_ID, tool_step, workflow
from tests.cli.test_experiment_rendering import FIRST_EXPERIMENT_ID, WORKFLOW_ID

UNKNOWN_ID = UUID("00000000-0000-4000-8000-0000000000ff")


def optimized(
    instance: api.Azathoth,
) -> UUID:
    """Optimize the word count workflow for one generation, and return the winning experiment."""

    return instance.optimization.optimize(
        COUNT_WORKFLOW_ID,
        counted(instance),
        target_latency_seconds=5.0,
        target_cost_usd=0.01,
    ).winning_experiment_id


def promote_command(
    workflow_id: UUID,
    experiment_id: UUID,
) -> str:
    """Return the command that promotes an experiment's winner."""

    return f"azathoth workflow promote {workflow_id} --experiment {experiment_id}"


def test_a_winner_measured_on_the_latest_revision_is_promotable(
    instance: api.Azathoth,
) -> None:
    experiment_id = optimized(instance)

    promotability = instance.experiments.promotable(experiment_id)

    assert promotability == api.Promotability(
        experiment_id=experiment_id,
        workflow_id=COUNT_WORKFLOW_ID,
        promotable=True,
        code=None,
        reason=None,
        command=promote_command(COUNT_WORKFLOW_ID, experiment_id),
    )
    build_parser().parse_args(shlex.split(promotability.command)[1:])
    assert instance.production.get(COUNT_WORKFLOW_ID) is None

    instance.production.promote(COUNT_WORKFLOW_ID, experiment_id=experiment_id)

    assert instance.production.get(COUNT_WORKFLOW_ID) is not None


def test_a_winner_measured_on_an_earlier_revision_is_not_promotable(
    instance: api.Azathoth,
) -> None:
    experiment_id = optimized(instance)
    instance.workflows.import_document(
        workflow(
            COUNT_WORKFLOW_ID, tool_step(COUNT_STEP_ID, "word_count", message="Counting again")
        )
    )

    promotability = instance.experiments.promotable(experiment_id)

    assert not promotability.promotable
    assert promotability.code == "candidate_rebuild"
    assert promotability.reason is not None
    assert "current revision is 2" in promotability.reason

    with pytest.raises(api.CandidateRebuildError):
        instance.production.promote(COUNT_WORKFLOW_ID, experiment_id=experiment_id)


def test_a_winner_of_a_workflow_no_longer_configured_is_not_promotable(
    location: str,
    instance: api.Azathoth,
) -> None:
    stocked(location)

    promotability = instance.experiments.promotable(FIRST_EXPERIMENT_ID)

    assert not promotability.promotable
    assert promotability.code == "not_found"
    assert promotability.reason == f"Workflow {WORKFLOW_ID} is not configured."


def test_an_unknown_experiment_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.ExperimentNotFoundError):
        instance.experiments.promotable(UNKNOWN_ID)


def test_a_comparison_names_the_promotion_command(
    location: str,
    instance: api.Azathoth,
) -> None:
    stocked(location)

    assert instance.experiments.compare(FIRST_EXPERIMENT_ID).command == promote_command(
        WORKFLOW_ID, FIRST_EXPERIMENT_ID
    )
