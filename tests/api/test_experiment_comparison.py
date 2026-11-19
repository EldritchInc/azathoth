"""Contract tests for comparing an experiment's winner with its baseline (ADR 0131)."""

from datetime import timedelta
from uuid import UUID

import pytest

from azathoth import api
from azathoth.context import Context
from azathoth.evaluation import EvaluationResult, EvaluationStatus
from azathoth.persistence.repositories import Repositories, open_repositories
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowExperimentRecord,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowSpecification,
    WorkflowStepRun,
    WorkflowStepSpecification,
)
from tests.cli.test_experiment_commands import STEP_ID, STRATEGY_ID
from tests.cli.test_experiment_rendering import (
    FIRST_CASE_ID,
    FIRST_EXPERIMENT_ID,
    LOSING_FIRST_RUN_ID,
    LOSING_OBSERVATION_ID,
    LOSING_SECOND_RUN_ID,
    SECOND_CASE_ID,
    WINNING_FIRST_EVALUATION_ID,
    WINNING_FIRST_RUN_ID,
    WINNING_OBSERVATION_ID,
    WINNING_SECOND_RUN_ID,
    create_experiment,
    create_metadata,
)
from tests.workflows.test_scoring import STARTED_AT, create_execution, create_successful_attempt

CONFIGURED_MODEL = "example-model"

CHEAPER_MODEL = "acme/small"

UNKNOWN_ID = UUID("00000000-0000-4000-8000-0000000000ff")


def kept_run(
    run_id: UUID,
    *,
    model: str,
    cost_usd: float | None,
    seconds: float,
) -> WorkflowRun:
    """Return one case run of one prompt step on `model`, costing and taking what it is given."""

    execution = create_execution(
        duration_seconds=seconds,
        estimated_cost_usd=cost_usd,
        provider="openrouter",
        model=model,
    )

    return WorkflowRun(
        id=run_id,
        workflow=create_metadata(),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                execution=execution,
                attempts=(create_successful_attempt(execution=execution),),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=STARTED_AT + timedelta(seconds=seconds),
    )


def production_on(
    model: str,
) -> WorkflowProductionState:
    """Return production running the workflow's prompt step on `model`."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=create_metadata(),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="Compared prompt",
                            description="The prompt production runs.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(text="Return exactly OK."),
                        model_selection=FixedModelSelection(provider="openrouter", model=model),
                    ),
                ),
            ),
        )
    )


def keep_runs(
    repositories: Repositories,
    *,
    winner_costs: tuple[float | None, float | None] = (0.01, 0.01),
    winner_seconds: tuple[float, float] = (2.0, 3.0),
) -> None:
    """Keep every case run: the configured candidate's, then the winner's, cheaper and faster."""

    for run_id in (LOSING_FIRST_RUN_ID, LOSING_SECOND_RUN_ID):
        repositories.runs.save(kept_run(run_id, model=CONFIGURED_MODEL, cost_usd=0.05, seconds=5.0))

    for run_id, cost, seconds in zip(
        (WINNING_FIRST_RUN_ID, WINNING_SECOND_RUN_ID), winner_costs, winner_seconds, strict=True
    ):
        repositories.runs.save(
            kept_run(run_id, model=CHEAPER_MODEL, cost_usd=cost, seconds=seconds)
        )


def stocked(
    location: str,
) -> Repositories:
    """Return the repositories of the database at `location`, holding the experiment."""

    stored = open_repositories(location)
    stored.experiments.save(create_experiment(FIRST_EXPERIMENT_ID))

    return stored


@pytest.fixture
def repositories(
    location: str,
) -> Repositories:
    """Return the instance's repositories, holding the experiment."""

    return stocked(location)


def test_without_production_the_winner_is_set_beside_the_configured_candidate(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)
    repositories.run_evaluations.save(
        WorkflowRunEvaluation(
            run_id=WINNING_FIRST_RUN_ID,
            evaluation=EvaluationResult(
                id=WINNING_FIRST_EVALUATION_ID,
                evaluator_name="exact",
                score=1.0,
                status=EvaluationStatus.PASSED,
                reason="It matched.",
            ),
        )
    )

    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert comparison.baseline == "configured"
    assert comparison.reason is None
    assert comparison.winner.observation_id == WINNING_OBSERVATION_ID
    assert comparison.baseline_candidate is not None
    assert comparison.baseline_candidate.observation_id == LOSING_OBSERVATION_ID
    assert comparison.steps == (
        api.ComparedStep(
            step_id=STEP_ID,
            winner_model=f"openrouter/{CHEAPER_MODEL}",
            baseline_model=f"openrouter/{CONFIGURED_MODEL}",
            differs=True,
        ),
    )
    first, second = comparison.cases
    assert (first.case_id, first.winner_passed, first.baseline_passed) == (
        FIRST_CASE_ID,
        True,
        True,
    )
    assert (second.case_id, second.winner_passed, second.baseline_passed) == (
        SECOND_CASE_ID,
        True,
        False,
    )
    assert (first.winner_score, first.baseline_score) == (1.0, None)


def test_each_side_costs_and_takes_the_mean_of_its_case_runs(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)

    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    winner, baseline = comparison.winner_runs, comparison.baseline_runs

    assert baseline is not None
    assert winner.runs == baseline.runs == 2
    assert winner.cost_usd == pytest.approx(0.01)
    assert winner.latency_seconds == pytest.approx(2.5)
    assert baseline.cost_usd == pytest.approx(0.05)
    assert baseline.latency_seconds == pytest.approx(5.0)


def test_a_run_of_unknown_cost_makes_its_sides_cost_unknown(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories, winner_costs=(None, 0.01))

    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert comparison.winner_runs.cost_usd is None
    assert comparison.winner_runs.latency_seconds == pytest.approx(2.5)
    assert comparison.baseline_runs is not None
    assert comparison.baseline_runs.cost_usd == pytest.approx(0.05)


def test_what_production_runs_is_the_baseline_when_the_experiment_holds_it(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)
    repositories.production_states.set(production_on(CONFIGURED_MODEL))

    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert comparison.baseline == "production"
    assert comparison.baseline_candidate is not None
    assert comparison.baseline_candidate.observation_id == LOSING_OBSERVATION_ID


def test_a_winner_production_already_runs_compares_nothing(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)
    repositories.production_states.set(production_on(CHEAPER_MODEL))

    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert comparison.baseline is None
    assert comparison.baseline_candidate is None
    assert comparison.reason == "Production already runs the winner."
    assert comparison.steps == ()
    assert comparison.baseline_runs is None
    assert comparison.winner.observation_id == WINNING_OBSERVATION_ID


def test_production_the_experiment_never_ran_falls_back_to_the_configured_candidate(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)
    repositories.production_states.set(production_on("acme/other"))

    assert instance.experiments.compare(FIRST_EXPERIMENT_ID).baseline == "configured"


def test_a_winner_that_is_the_configured_candidate_compares_nothing(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    record = create_experiment(FIRST_EXPERIMENT_ID)
    reversed_record = WorkflowExperimentRecord(
        id=UUID("55555555-5555-4555-8555-555555555558"),
        benchmark_id=record.benchmark_id,
        observations=tuple(reversed(record.observations)),
        ranking=record.ranking,
        recorded_at=record.recorded_at,
    )
    repositories.experiments.save(reversed_record)

    comparison = instance.experiments.compare(reversed_record.id)

    assert comparison.baseline is None
    assert comparison.reason == "The winner is the candidate the workflow is configured with."


def test_a_comparison_without_kept_runs_still_compares_outcomes(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert comparison.baseline == "configured"
    assert comparison.steps == ()
    assert comparison.winner_runs == api.RunCosts(runs=0, cost_usd=None, latency_seconds=None)
    assert [case.baseline_passed for case in comparison.cases] == [True, False]


def test_an_unknown_experiment_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.ExperimentNotFoundError):
        instance.experiments.compare(UNKNOWN_ID)


def test_a_comparison_is_its_own_json(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)
    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert api.ExperimentComparison.model_validate_json(comparison.model_dump_json()) == comparison
