"""A workflow's recorded optimization experiments, through the service API (ADR 0131).

An experiment records the content digest of the benchmark its candidates
ran, not its revision number, so the revision is told from the benchmark's
history, as an execution's is (ADR 0130). A candidate's steps are read from
its first case's run, which says what each step ran on.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from azathoth.api.browsing import LIMIT_MESSAGE, RepositoriesAccess
from azathoth.api.errors import ExperimentNotFoundError, InvalidArgumentError, NotFoundError
from azathoth.api.models import (
    CandidateScorecard,
    ComparedCase,
    ComparedStep,
    ComparisonBaseline,
    ExperimentCandidate,
    ExperimentCase,
    ExperimentComparison,
    ExperimentDetail,
    ExperimentHeader,
    ExperimentStep,
    ExperimentSummary,
    RunCosts,
    Savings,
    SavingsProjection,
)
from azathoth.evaluation import BenchmarkDatasetRevision
from azathoth.persistence.repositories import Repositories
from azathoth.prompting import PROMPT_SPECIFICATIONS, FixedModelSelection
from azathoth.sensitivity import effective_sensitivity
from azathoth.workflows import (
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowScorecard,
)

PRODUCTION_RUNS_WINNER: Final = "Production already runs the winner."

WINNER_IS_CONFIGURED: Final = "The winner is the candidate the workflow is configured with."

PROJECTION_DAYS: Final = 30
"""How many days of production invocations a saving is projected over."""

NO_BASELINE: Final = "The experiment holds neither what production runs nor what is configured."


def experiment_not_found_message(
    experiment_id: UUID,
) -> str:
    """Return what an experiment that was never recorded is refused with."""

    return f"Experiment {experiment_id} was not found."


def experiment_command(
    experiment_id: UUID,
) -> str:
    """Return the command that shows one experiment."""

    return f"azathoth experiment show {experiment_id}"


def experiment_revision(
    history: Sequence[BenchmarkDatasetRevision],
    experiment: WorkflowExperimentRecord,
) -> int | None:
    """Return the benchmark revision an experiment ran: the latest holding its content."""

    if experiment.benchmark_digest is None:
        return None

    matching = [
        revision for revision in history if revision.content_digest == experiment.benchmark_digest
    ]

    return matching[-1].number if matching else None


def _header(
    experiment: WorkflowExperimentRecord,
    revision: int | None,
) -> ExperimentHeader:
    """Return what every view of an experiment carries."""

    winner = experiment.winner

    return ExperimentHeader(
        experiment_id=experiment.id,
        workflow_id=winner.workflow.id,
        workflow_name=winner.workflow.name,
        recorded_at=experiment.recorded_at,
        benchmark_id=experiment.benchmark_id,
        benchmark_digest=experiment.benchmark_digest,
        benchmark_revision=revision,
        sensitivity=effective_sensitivity(experiment.sensitivity),
        candidate_count=len(experiment.observations),
        case_count=len(winner.cases),
        winner_observation_id=winner.id,
        command=experiment_command(experiment.id),
    )


def experiment_summary(
    experiment: WorkflowExperimentRecord,
    *,
    revision: int | None = None,
) -> ExperimentSummary:
    """Return what a workflow's list of experiments shows of one."""

    return ExperimentSummary(
        **_header(experiment, revision).model_dump(),
        winner_score=experiment.winner.scorecard.overall_score,
    )


def candidate_scorecard(
    scorecard: WorkflowScorecard,
) -> CandidateScorecard:
    """Return the API's view of one candidate's scores."""

    return CandidateScorecard(
        quality_score=scorecard.quality_score,
        reliability_score=scorecard.reliability_score,
        latency_score=scorecard.latency_score,
        cost_score=scorecard.cost_score,
        citation_score=scorecard.citation_score,
        overall_score=scorecard.overall_score,
        rationale=scorecard.rationale,
    )


def _steps(
    run: WorkflowRun | None,
) -> tuple[ExperimentStep, ...]:
    """Return each step of a candidate as one of its runs ran it, or none without the run."""

    if run is None:
        return ()

    steps: list[ExperimentStep] = []

    for step in run.steps:
        execution = step.execution
        metrics = execution.metrics if execution is not None else None
        model = (
            f"{metrics.provider}/{metrics.model}"
            if metrics is not None and metrics.provider is not None and metrics.model is not None
            else None
        )

        steps.append(
            ExperimentStep(
                step_id=step.step_id,
                strategy_id=execution.strategy_id if execution is not None else None,
                model=model,
            )
        )

    return tuple(steps)


def _candidate(
    observation: WorkflowExperimentObservation,
    rank: int,
    runs: Mapping[UUID, WorkflowRun],
) -> ExperimentCandidate:
    """Return one candidate of an experiment, in its place."""

    return ExperimentCandidate(
        observation_id=observation.id,
        rank=rank,
        workflow_revision=observation.candidate_signature.workflow_revision,
        strategy_ids=observation.candidate_signature.strategy_ids,
        steps=_steps(runs.get(observation.cases[0].run_id)),
        cases_run=len(observation.cases),
        cases_passed=observation.cases_passed,
        scorecard=candidate_scorecard(observation.scorecard),
        judge_calls=observation.judge_calls,
        judge_cost_usd=observation.judge_cost_usd,
        cases=tuple(
            ExperimentCase(
                case_id=case.case_id,
                run_id=case.run_id,
                evaluation_id=case.evaluation_id,
                passed=case.passed,
                judge_calls=case.judge_calls,
                judge_cost_usd=case.judge_cost_usd,
            )
            for case in observation.cases
        ),
    )


def experiment_detail(
    experiment: WorkflowExperimentRecord,
    *,
    revision: int | None = None,
    runs: Mapping[UUID, WorkflowRun] | None = None,
) -> ExperimentDetail:
    """Return one experiment with every candidate ranked, its steps read from `runs`."""

    kept = runs if runs is not None else {}

    return ExperimentDetail(
        **_header(experiment, revision).model_dump(),
        candidates=tuple(
            _candidate(observation, rank, kept)
            for rank, observation in enumerate(experiment.ranked_observations, start=1)
        ),
    )


def first_runs(
    repositories: Repositories,
    experiment: WorkflowExperimentRecord,
) -> dict[UUID, WorkflowRun]:
    """Return each candidate's first case run that is still kept, by its ID."""

    found: dict[UUID, WorkflowRun] = {}

    for observation in experiment.observations:
        run_id = observation.cases[0].run_id
        run = repositories.runs.get(run_id)

        if run is not None:
            found[run_id] = run

    return found


def recorded_experiment(
    repositories: Repositories,
    experiment_id: UUID,
) -> WorkflowExperimentRecord:
    """Return one recorded experiment.

    Raises:
        ExperimentNotFoundError: No experiment has this ID.
    """

    experiment = repositories.experiments.get(experiment_id)

    if experiment is None:
        raise ExperimentNotFoundError(experiment_not_found_message(experiment_id))

    return experiment


def _production_models(
    state: WorkflowProductionState,
) -> dict[UUID, str]:
    """Return the model production pins each prompt step to, by step."""

    return {
        step.id: selection.identifier
        for step in state.specification.steps
        if isinstance(step.specification, PROMPT_SPECIFICATIONS)
        and isinstance(selection := step.specification.model_selection, FixedModelSelection)
    }


def _runs_production(
    candidate: ExperimentCandidate,
    state: WorkflowProductionState,
) -> bool:
    """Return whether a candidate is what production runs: each prompt step on its model."""

    if (
        state.specification_revision is not None
        and candidate.workflow_revision is not None
        and state.specification_revision != candidate.workflow_revision
    ):
        return False

    ran = {step.step_id: step.model for step in candidate.steps}

    return all(ran.get(step_id) == model for step_id, model in _production_models(state).items())


def _baseline(
    candidates: Sequence[ExperimentCandidate],
    recorded_first: UUID,
    production: WorkflowProductionState | None,
) -> tuple[ComparisonBaseline | None, ExperimentCandidate | None, str | None]:
    """Return what the winner is compared against, the candidate it is, or why there is none.

    What production runs comes first, since promoting replaces it; then the
    configured candidate, which every experiment of a session runs first.
    """

    winner = candidates[0]

    if production is not None:
        running = next(
            (candidate for candidate in candidates if _runs_production(candidate, production)),
            None,
        )

        if running is winner:
            return None, None, PRODUCTION_RUNS_WINNER

        if running is not None:
            return "production", running, None

    configured = next(
        (candidate for candidate in candidates if candidate.observation_id == recorded_first),
        None,
    )

    if configured is None:
        return None, None, NO_BASELINE

    if configured is winner:
        return None, None, WINNER_IS_CONFIGURED

    return "configured", configured, None


def _run_cost(
    run: WorkflowRun,
) -> float | None:
    """Return what one run cost, or None when a step's cost is unknown."""

    total = 0.0

    for step in run.steps:
        if step.execution is None:
            continue

        metrics = step.execution.metrics

        if metrics is None or metrics.estimated_cost_usd is None:
            return None

        total += metrics.estimated_cost_usd

    return total


def run_costs(
    repositories: Repositories,
    candidate: ExperimentCandidate,
) -> RunCosts:
    """Return the mean cost and time of a candidate's case runs that are still kept."""

    kept = [
        run for case in candidate.cases if (run := repositories.runs.get(case.run_id)) is not None
    ]

    if not kept:
        return RunCosts(runs=0, cost_usd=None, latency_seconds=None)

    costs = [_run_cost(run) for run in kept]

    return RunCosts(
        runs=len(kept),
        cost_usd=(
            None
            if any(cost is None for cost in costs)
            else sum(cost for cost in costs if cost is not None) / len(kept)
        ),
        latency_seconds=sum(run.duration_seconds for run in kept) / len(kept),
    )


def _score(
    repositories: Repositories,
    evaluation_id: UUID,
) -> float | None:
    """Return an evaluation's score while it is kept."""

    kept = repositories.run_evaluations.get(evaluation_id)

    return kept.evaluation.score if kept is not None else None


def _compared_steps(
    winner: ExperimentCandidate,
    baseline: ExperimentCandidate,
) -> tuple[ComparedStep, ...]:
    """Return each step either side ran, in the winner's order, then the baseline's own."""

    winning = {step.step_id: step.model for step in winner.steps}
    base = {step.step_id: step.model for step in baseline.steps}
    order = [*winning, *(step_id for step_id in base if step_id not in winning)]

    return tuple(
        ComparedStep(
            step_id=step_id,
            winner_model=winning.get(step_id),
            baseline_model=base.get(step_id),
            differs=winning.get(step_id) != base.get(step_id),
        )
        for step_id in order
    )


def _compared_case(
    repositories: Repositories,
    case: ExperimentCase,
    other: ExperimentCase | None,
) -> ComparedCase:
    """Return one case as the winner did on it, and the baseline in the same place."""

    return ComparedCase(
        case_id=case.case_id,
        winner_passed=case.passed,
        baseline_passed=None if other is None else other.passed,
        winner_score=_score(repositories, case.evaluation_id),
        baseline_score=None if other is None else _score(repositories, other.evaluation_id),
    )


def _saved(
    baseline: float | None,
    winner: float | None,
) -> tuple[float | None, float | None]:
    """Return what the winner saves on one measure, and that as a percentage of the baseline."""

    if baseline is None or winner is None:
        return None, None

    saved = baseline - winner

    return saved, (saved / baseline * 100.0 if baseline > 0 else None)


def savings_of(
    winner: RunCosts,
    baseline: RunCosts,
) -> Savings:
    """Return what the winner saves per run over the baseline, measured."""

    cost, cost_percent = _saved(baseline.cost_usd, winner.cost_usd)
    latency, latency_percent = _saved(baseline.latency_seconds, winner.latency_seconds)

    return Savings(
        cost_usd=cost,
        cost_percent=cost_percent,
        latency_seconds=latency,
        latency_percent=latency_percent,
    )


def projection_of(
    repositories: Repositories,
    workflow_id: UUID,
    savings: Savings,
    now: datetime,
) -> SavingsProjection | None:
    """Return the saving over production's invocations in the window before `now`, if any."""

    since = now - timedelta(days=PROJECTION_DAYS)
    invocations = sum(
        invocation.created_at >= since
        for invocation in repositories.invocations.invocations_for_workflow(workflow_id)
    )

    if not invocations:
        return None

    return SavingsProjection(
        window_days=PROJECTION_DAYS,
        since=since,
        invocations=invocations,
        cost_usd=None if savings.cost_usd is None else savings.cost_usd * invocations,
        latency_seconds=(
            None if savings.latency_seconds is None else savings.latency_seconds * invocations
        ),
    )


def compare_experiment(
    repositories: Repositories,
    experiment: WorkflowExperimentRecord,
    *,
    now: datetime | None = None,
) -> ExperimentComparison:
    """Return an experiment's winner set beside its baseline, with what each run cost and took.

    What the winner saves is measured per run on the benchmark, and projected
    over production's invocations in the 30 days before `now`.
    """

    detail = experiment_detail(experiment, runs=first_runs(repositories, experiment))
    winner = detail.candidates[0]
    baseline, compared, reason = _baseline(
        detail.candidates,
        experiment.observations[0].id,
        repositories.production_states.get(detail.workflow_id),
    )

    winner_runs = run_costs(repositories, winner)
    baseline_runs = None if compared is None else run_costs(repositories, compared)
    savings = None if baseline_runs is None else savings_of(winner_runs, baseline_runs)

    return ExperimentComparison(
        experiment_id=detail.experiment_id,
        workflow_id=detail.workflow_id,
        baseline=baseline,
        reason=reason,
        winner=winner,
        baseline_candidate=compared,
        steps=() if compared is None else _compared_steps(winner, compared),
        cases=tuple(
            _compared_case(
                repositories,
                case,
                compared.cases[index]
                if compared is not None and index < len(compared.cases)
                else None,
            )
            for index, case in enumerate(winner.cases)
        ),
        winner_runs=winner_runs,
        baseline_runs=baseline_runs,
        savings=savings,
        projection=(
            None
            if savings is None
            else projection_of(
                repositories,
                detail.workflow_id,
                savings,
                now if now is not None else datetime.now(UTC),
            )
        ),
    )


class Experiments:
    """The optimization experiments an instance has recorded, read and compared."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
    ) -> None:
        """Read experiments from `repositories`."""

        self._repositories = repositories

    def list(
        self,
        workflow_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[ExperimentSummary, ...]:
        """Return a workflow's experiments, newest first, at most `limit`.

        A workflow since removed from configuration still lists its
        experiments, as `workflow experiments` lists them. It is the
        `read_runs` action (ADR 0131).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: The workflow is neither configured nor in any
                experiment.
        """

        if limit is not None and limit < 1:
            raise InvalidArgumentError(LIMIT_MESSAGE)

        repositories = self._repositories()
        recorded = repositories.experiments.experiments_for_workflow(workflow_id)

        if not recorded and repositories.workflows.get(workflow_id) is None:
            raise NotFoundError(f"Workflow {workflow_id} is not configured.")

        newest_first = sorted(
            recorded,
            key=lambda experiment: experiment.recorded_at,
            reverse=True,
        )
        histories: dict[UUID, tuple[BenchmarkDatasetRevision, ...]] = {}

        def revision_of(
            experiment: WorkflowExperimentRecord,
        ) -> int | None:
            """Return the benchmark revision one experiment ran, reading each history once."""

            if experiment.benchmark_id is None:
                return None

            if experiment.benchmark_id not in histories:
                histories[experiment.benchmark_id] = tuple(
                    repositories.benchmarks.revisions(experiment.benchmark_id)
                )

            return experiment_revision(histories[experiment.benchmark_id], experiment)

        return tuple(
            experiment_summary(experiment, revision=revision_of(experiment))
            for experiment in newest_first[:limit]
        )

    def get(
        self,
        experiment_id: UUID,
    ) -> ExperimentDetail:
        """Return one experiment, with every candidate ranked and every case.

        Each candidate's steps name the models its first case's run ran on,
        while that run is kept. It is the `read_runs` action (ADR 0131).

        Raises:
            InstanceClosedError: The instance was closed.
            ExperimentNotFoundError: No experiment has this ID.
        """

        repositories = self._repositories()
        experiment = recorded_experiment(repositories, experiment_id)
        history = (
            repositories.benchmarks.revisions(experiment.benchmark_id)
            if experiment.benchmark_id is not None
            else ()
        )

        return experiment_detail(
            experiment,
            revision=experiment_revision(history, experiment),
            runs=first_runs(repositories, experiment),
        )

    def compare(
        self,
        experiment_id: UUID,
    ) -> ExperimentComparison:
        """Return an experiment's winner set beside what promoting it would replace.

        The baseline is what production runs now, when the experiment holds
        it, and otherwise the workflow's configured candidate, which every
        experiment of a session runs first. Each side's cost and time are the
        means over its case runs still kept. It reads durable state only,
        and is the `read_runs` action (ADR 0131).

        Raises:
            InstanceClosedError: The instance was closed.
            ExperimentNotFoundError: No experiment has this ID.
        """

        repositories = self._repositories()

        return compare_experiment(repositories, recorded_experiment(repositories, experiment_id))


__all__ = [
    "NO_BASELINE",
    "PRODUCTION_RUNS_WINNER",
    "WINNER_IS_CONFIGURED",
    "Experiments",
    "PROJECTION_DAYS",
    "compare_experiment",
    "projection_of",
    "savings_of",
    "run_costs",
    "candidate_scorecard",
    "experiment_detail",
    "experiment_summary",
]
