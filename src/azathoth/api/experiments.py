"""A workflow's recorded optimization experiments, through the service API (ADR 0131).

An experiment records the content digest of the benchmark its candidates
ran, not its revision number, so the revision is told from the benchmark's
history, as an execution's is (ADR 0130). A candidate's steps are read from
its first case's run, which says what each step ran on.
"""

from collections.abc import Mapping, Sequence
from uuid import UUID

from azathoth.api.browsing import LIMIT_MESSAGE, RepositoriesAccess
from azathoth.api.errors import ExperimentNotFoundError, InvalidArgumentError, NotFoundError
from azathoth.api.models import (
    CandidateScorecard,
    ExperimentCandidate,
    ExperimentCase,
    ExperimentDetail,
    ExperimentHeader,
    ExperimentStep,
    ExperimentSummary,
)
from azathoth.evaluation import BenchmarkDatasetRevision
from azathoth.persistence.repositories import Repositories
from azathoth.sensitivity import effective_sensitivity
from azathoth.workflows import (
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowRun,
    WorkflowScorecard,
)


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


__all__ = [
    "Experiments",
    "candidate_scorecard",
    "experiment_detail",
    "experiment_summary",
]
