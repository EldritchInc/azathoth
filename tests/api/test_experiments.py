"""Contract tests for reading a workflow's experiments through the service API (ADR 0131)."""

import shlex
from datetime import timedelta
from uuid import UUID

import pytest

from azathoth import api
from azathoth.cli import render_workflow_experiment, render_workflow_experiment_summaries
from azathoth.cli.parsing import build_parser
from azathoth.context import Context
from azathoth.evaluation import BenchmarkDataset
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import WorkflowRun, WorkflowStepRun
from tests.cli.test_experiment_commands import create_workflow
from tests.cli.test_experiment_rendering import (
    BENCHMARK_ID,
    FIRST_CASE_ID,
    FIRST_EXPERIMENT_ID,
    LEGACY_WINNING_RUN_ID,
    LOSING_OBSERVATION_ID,
    RECORDED_AT,
    SECOND_CASE_ID,
    SECOND_EXPERIMENT_ID,
    SECOND_STRATEGY_ID,
    WINNING_FIRST_EVALUATION_ID,
    WINNING_FIRST_RUN_ID,
    WINNING_OBSERVATION_ID,
    WORKFLOW_ID,
    create_experiment,
    create_legacy_experiment,
    create_metadata,
)
from tests.workflows.test_scoring import (
    STARTED_AT,
    STRATEGY_ID,
    create_execution,
    create_successful_attempt,
)

LEGACY_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555553")

STEP_ID = UUID("88888888-8888-4888-8888-888888888881")

TOOL_STEP_ID = UUID("88888888-8888-4888-8888-888888888882")

UNKNOWN_ID = UUID("00000000-0000-4000-8000-0000000000ff")


def parses(
    command: str,
) -> bool:
    """Return whether the CLI accepts one command an API value carries."""

    words = shlex.split(command)

    assert words[0] == "azathoth"

    build_parser().parse_args(words[1:])

    return True


def winning_run() -> WorkflowRun:
    """Return the run the winner's first case ran as: a model step, then a step with no model."""

    model_step = create_execution(
        strategy_id=SECOND_STRATEGY_ID,
        provider="openrouter",
        model="acme/small",
    )
    tool_step = create_execution(provider=None, model=None)

    return WorkflowRun(
        id=WINNING_FIRST_RUN_ID,
        workflow=create_metadata(),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                execution=model_step,
                attempts=(create_successful_attempt(execution=model_step),),
            ),
            WorkflowStepRun(
                step_id=TOOL_STEP_ID,
                layer_index=1,
                execution=tool_step,
                attempts=(create_successful_attempt(execution=tool_step),),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=STARTED_AT + timedelta(seconds=5),
    )


@pytest.fixture
def stocked(
    location: str,
    instance: api.Azathoth,
) -> api.Azathoth:
    """Return the instance holding a restricted experiment, a later one, and a legacy one.

    The first names the benchmark's content, so its revision can be told,
    and its winner's first case run is kept.
    """

    repositories = open_repositories(location)
    revision = repositories.benchmarks.save(
        BenchmarkDataset(id=BENCHMARK_ID, name="classify", description="Classify.")
    )

    repositories.experiments.save(
        create_experiment(FIRST_EXPERIMENT_ID).model_copy(
            update={
                "benchmark_digest": revision.content_digest,
                "sensitivity": Sensitivity.RESTRICTED,
            }
        )
    )
    repositories.experiments.save(
        create_experiment(SECOND_EXPERIMENT_ID).model_copy(
            update={"recorded_at": RECORDED_AT + timedelta(hours=1)}
        )
    )
    repositories.experiments.save(
        create_legacy_experiment().model_copy(
            update={
                "id": LEGACY_EXPERIMENT_ID,
                "recorded_at": RECORDED_AT - timedelta(hours=1),
            }
        )
    )
    repositories.runs.save(winning_run())

    return instance


def test_a_workflows_experiments_are_listed_newest_first(
    stocked: api.Azathoth,
) -> None:
    listed = stocked.experiments.list(WORKFLOW_ID)

    assert [summary.experiment_id for summary in listed] == [
        SECOND_EXPERIMENT_ID,
        FIRST_EXPERIMENT_ID,
        LEGACY_EXPERIMENT_ID,
    ]
    assert [
        summary.experiment_id for summary in stocked.experiments.list(WORKFLOW_ID, limit=1)
    ] == [SECOND_EXPERIMENT_ID]
    assert all(parses(summary.command) for summary in listed)


def test_a_summary_says_what_ran_and_which_candidate_won(
    stocked: api.Azathoth,
) -> None:
    _, first, legacy = stocked.experiments.list(WORKFLOW_ID)

    assert first.workflow_id == WORKFLOW_ID
    assert first.workflow_name == "rendered workflow"
    assert first.recorded_at == RECORDED_AT
    assert (first.benchmark_id, first.benchmark_revision) == (BENCHMARK_ID, 1)
    assert first.sensitivity == "restricted"
    assert (first.candidate_count, first.case_count) == (2, 2)
    assert first.winner_observation_id == WINNING_OBSERVATION_ID
    assert first.winner_score == pytest.approx(0.9)
    assert first.command == f"azathoth experiment show {FIRST_EXPERIMENT_ID}"
    assert (legacy.benchmark_id, legacy.benchmark_digest, legacy.benchmark_revision) == (
        None,
        None,
        None,
    )
    assert legacy.sensitivity == "internal"
    assert legacy.case_count == 1


def test_a_configured_workflow_without_experiments_has_none(
    location: str,
    instance: api.Azathoth,
) -> None:
    open_repositories(location).workflows.save(create_workflow())

    assert instance.experiments.list(WORKFLOW_ID) == ()


def test_an_unknown_workflow_or_a_limit_below_one_is_refused(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=rf"^Workflow {UNKNOWN_ID} is not configured\.$"):
        stocked.experiments.list(UNKNOWN_ID)

    with pytest.raises(api.InvalidArgumentError, match=r"^A history limit must be at least 1\.$"):
        stocked.experiments.list(WORKFLOW_ID, limit=0)


def test_an_experiment_is_read_with_every_candidate_ranked(
    stocked: api.Azathoth,
) -> None:
    detail = stocked.experiments.get(FIRST_EXPERIMENT_ID)
    winner, loser = detail.candidates

    assert detail.experiment_id == FIRST_EXPERIMENT_ID
    assert detail.sensitivity == "restricted"
    assert detail.benchmark_revision == 1
    assert (winner.rank, winner.observation_id) == (1, WINNING_OBSERVATION_ID)
    assert (loser.rank, loser.observation_id) == (2, LOSING_OBSERVATION_ID)
    assert winner.strategy_ids == (SECOND_STRATEGY_ID,)
    assert (winner.cases_run, winner.cases_passed) == (2, 2)
    assert (loser.cases_run, loser.cases_passed) == (2, 1)
    assert winner.scorecard.overall_score == pytest.approx(0.9)
    assert winner.scorecard.rationale == "Correct and inexpensive."
    assert winner.scorecard.citation_score is None
    assert (winner.judge_calls, winner.judge_cost_usd) == (0, 0.0)
    assert [case.case_id for case in winner.cases] == [FIRST_CASE_ID, SECOND_CASE_ID]
    first_case = winner.cases[0]
    assert (first_case.run_id, first_case.evaluation_id, first_case.passed) == (
        WINNING_FIRST_RUN_ID,
        WINNING_FIRST_EVALUATION_ID,
        True,
    )
    assert detail.command == f"azathoth experiment show {FIRST_EXPERIMENT_ID}"


def test_a_candidates_steps_name_the_models_its_runs_ran_on(
    stocked: api.Azathoth,
) -> None:
    winner, loser = stocked.experiments.get(FIRST_EXPERIMENT_ID).candidates

    assert [(step.step_id, step.strategy_id, step.model) for step in winner.steps] == [
        (STEP_ID, SECOND_STRATEGY_ID, "openrouter/acme/small"),
        (TOOL_STEP_ID, STRATEGY_ID, None),
    ]
    assert loser.steps == ()


def test_a_legacy_experiment_reads_what_it_lacks_as_none(
    stocked: api.Azathoth,
) -> None:
    detail = stocked.experiments.get(LEGACY_EXPERIMENT_ID)
    winner = detail.candidates[0]

    assert detail.benchmark_id is None
    assert winner.observation_id == LEGACY_WINNING_RUN_ID
    assert winner.cases_passed is None
    (case,) = winner.cases
    assert (case.case_id, case.passed) == (None, None)


def test_an_unknown_experiment_is_not_found(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(
        api.ExperimentNotFoundError, match=rf"^Experiment {UNKNOWN_ID} was not found\.$"
    ):
        stocked.experiments.get(UNKNOWN_ID)


def test_the_command_line_renders_what_the_api_reads_as_it_rendered_the_record(
    stocked: api.Azathoth,
) -> None:
    record = create_experiment(SECOND_EXPERIMENT_ID).model_copy(
        update={"recorded_at": RECORDED_AT + timedelta(hours=1)}
    )

    assert render_workflow_experiment(stocked.experiments.get(SECOND_EXPERIMENT_ID)) == (
        render_workflow_experiment(record)
    )
    assert render_workflow_experiment_summaries(stocked.experiments.list(WORKFLOW_ID)[:1]) == (
        render_workflow_experiment_summaries((record,))
    )
    assert render_workflow_experiment(stocked.experiments.get(LEGACY_EXPERIMENT_ID)) == (
        render_workflow_experiment(
            create_legacy_experiment().model_copy(
                update={
                    "id": LEGACY_EXPERIMENT_ID,
                    "recorded_at": RECORDED_AT - timedelta(hours=1),
                }
            )
        )
    )
