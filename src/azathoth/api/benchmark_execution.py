"""Executing configured workflows against benchmarks (ADRs 0040, 0075 and 0130).

The service API's `benchmarks.run` and `benchmarks.compare`, and the
command line's `benchmark run` and `benchmark compare`, execute through
these same calls, as `run resume` and `runs.resume` share theirs (ADR
0129), so the two cannot come to execute a benchmark differently. The
checks that refuse a benchmark before any case runs are here too, each
returning why, for each caller to report as it reports.
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Final, Protocol, TypeVar
from uuid import UUID

from pydantic import ValidationError

from azathoth.api.errors import (
    InvalidArgumentError,
    JudgeUnavailableError,
    NotFoundError,
    RunCancelledError,
    RunNotStartedError,
    WorkflowResultMissingError,
)
from azathoth.api.models import BenchmarkEvent, CaseFinished, CaseStarted
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeComparison,
    OutcomeEvaluator,
    SemanticJudgingError,
    UnsupportedComparisonError,
)
from azathoth.persistence.repositories import Repositories
from azathoth.runtime import JudgeUnavailableError as RuntimeJudgeUnavailableError
from azathoth.runtime import RuntimeEnvironment, WorkflowNotConfiguredError
from azathoth.sensitivity import Sensitivity, most_sensitive
from azathoth.workflows import (
    BenchmarkCaseObserver,
    WorkflowBenchmarkCaseResult,
    WorkflowBenchmarkComparator,
    WorkflowBenchmarkEvidenceRecorder,
    WorkflowBenchmarkRanker,
    WorkflowBenchmarkRanking,
    WorkflowBenchmarkResult,
    WorkflowBenchmarkRunner,
    WorkflowBenchmarkScorer,
    WorkflowCandidate,
    WorkflowGenerationError,
    WorkflowResultError,
    WorkflowRunner,
    WorkflowScoringPolicy,
)


def case_runner(
    stored: Repositories,
) -> WorkflowRunner:
    """Return the runner benchmark cases and experiments run in (ADR 0117).

    A case's run journals as any run does, indexes the children its steps
    start, and is given the database's content, so its tools read the
    documents it was given, its prompts the extractions its steps kept, and
    a step that starts children costs what they did, as a run of `workflow
    run` would.
    """

    return WorkflowRunner(
        journal=stored.run_journal,
        children=stored.run_children,
        content=stored.tool_content,
    )


async def execute_configured_benchmark(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    dataset: BenchmarkDataset,
    runner: WorkflowBenchmarkRunner | None = None,
    recorder: WorkflowBenchmarkEvidenceRecorder | None = None,
    workflow_runner: WorkflowRunner | None = None,
    observer: BenchmarkCaseObserver | None = None,
) -> WorkflowBenchmarkResult:
    """Execute one configured workflow against a benchmark dataset.

    Without an explicit runner, semantic cases are judged by the runtime's
    judge rotation, resolved before any case executes. The workflow candidate
    is generated once, before any case executes, and runs every case, so the
    whole benchmark judges one resolved configuration.

    With a recorder, every case run, every evaluation, and one execution
    record sharing the result's identity are saved. Without an explicit
    runner, every case runs in the given workflow runner (ADR 0117).

    Raises:
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
        WorkflowNotConfiguredError: The workflow is not configured.
        WorkflowGenerationError: The workflow cannot be generated.
    """

    benchmark_runner = (
        runner
        if runner is not None
        else WorkflowBenchmarkRunner(
            runner=workflow_runner,
            evaluator=_outcome_evaluator(
                runtime,
                dataset,
            ),
        )
    )

    candidate = runtime.generate_workflow_candidate(
        workflow_id,
        sensitivity=dataset.sensitivity,
    )

    result = (
        await benchmark_runner.run(dataset, _every_case(candidate))
        if observer is None
        else await benchmark_runner.run(dataset, _every_case(candidate), observer=observer)
    )

    if recorder is not None:
        recorder.record_run(
            result,
            candidate=candidate,
        )

    return result


async def compare_configured_benchmarks(
    *,
    runtime: RuntimeEnvironment,
    workflow_ids: tuple[UUID, ...],
    dataset: BenchmarkDataset,
    scoring_policy: WorkflowScoringPolicy,
    comparator: WorkflowBenchmarkComparator | None = None,
    recorder: WorkflowBenchmarkEvidenceRecorder | None = None,
    workflow_runner: WorkflowRunner | None = None,
    observer: BenchmarkCaseObserver | None = None,
) -> WorkflowBenchmarkRanking:
    """Compare configured workflows against one benchmark dataset.

    Without an explicit comparator, semantic cases are judged by the runtime's
    judge rotation, resolved before any case executes. Every workflow
    candidate is generated once, before any case executes.

    With a recorder, every case run, every evaluation, and one execution
    record sharing the ranking's identity are saved, together with the
    scoring policy that produced the ranking. Without an explicit
    comparator, every case runs in the given workflow runner (ADR 0117).

    Raises:
        ValueError: Fewer than two workflows, or duplicate workflows.
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
        WorkflowNotConfiguredError: A workflow is not configured.
        WorkflowGenerationError: A workflow cannot be generated.
    """

    if len(workflow_ids) < 2:
        raise ValueError("At least two configured workflows are required for benchmark comparison.")

    if len(workflow_ids) != len(set(workflow_ids)):
        raise ValueError("Configured benchmark workflow identifiers must be unique.")

    benchmark_comparator = (
        comparator
        if comparator is not None
        else WorkflowBenchmarkComparator(
            runner=WorkflowBenchmarkRunner(
                runner=workflow_runner,
                evaluator=_outcome_evaluator(
                    runtime,
                    dataset,
                ),
            ),
        )
    )

    candidates = {
        str(workflow_id): runtime.generate_workflow_candidate(
            workflow_id,
            sensitivity=dataset.sensitivity,
        )
        for workflow_id in workflow_ids
    }

    factories = {name: _every_case(candidate) for name, candidate in candidates.items()}
    comparison = (
        await benchmark_comparator.compare(dataset, factories)
        if observer is None
        else await benchmark_comparator.compare(dataset, factories, observer=observer)
    )

    scorer = WorkflowBenchmarkScorer(
        policy=scoring_policy,
    )

    ranker = WorkflowBenchmarkRanker(
        scorer=scorer,
    )

    ranking = ranker.rank(
        comparison,
    )

    if recorder is not None:
        recorder.record_comparison(
            comparison,
            ranking,
            candidates=candidates,
            scoring_policy=scoring_policy,
        )

    return ranking


def _every_case(
    candidate: WorkflowCandidate,
) -> Callable[[BenchmarkCase], WorkflowCandidate]:
    """Return a candidate factory that runs one candidate for every case."""

    def factory(
        _case: BenchmarkCase,
    ) -> WorkflowCandidate:
        """Return the pre-generated candidate."""

        return candidate

    return factory


def _outcome_evaluator(
    runtime: RuntimeEnvironment,
    dataset: BenchmarkDataset,
) -> OutcomeEvaluator:
    """Return the runtime evaluator, with judges only when the dataset needs them.

    Judges see what the semantic cases' runs return, so every judge must be
    allowed to receive the most sensitive of those cases (ADR 0123).

    Raises:
        JudgeUnavailableError: The dataset has semantic cases and a judge
            cannot be used.
    """

    return runtime.outcome_evaluator(
        semantic=dataset.uses_comparison(OutcomeComparison.SEMANTIC),
        sensitivity=judged_sensitivity(dataset),
    )


def judged_sensitivity(
    dataset: BenchmarkDataset,
) -> Sensitivity:
    """Return the label of what a dataset's judges are sent: its semantic cases' (ADR 0123)."""

    return most_sensitive(
        case.sensitivity
        for case in dataset.cases
        if case.expected.comparison is OutcomeComparison.SEMANTIC
    )


def missing_cases(
    dataset: BenchmarkDataset,
) -> str | None:
    """Return why a benchmark with no cases cannot run, or None when it has some."""

    return None if dataset.cases else f"Benchmark {dataset.id} has no cases."


@dataclass(frozen=True)
class ComparisonProblem:
    """Why a case's comparison cannot be evaluated, and whether a judge is what is missing."""

    message: str
    needs_judge: bool


def unsupported_comparison(
    repositories: Repositories,
    dataset: BenchmarkDataset,
) -> ComparisonProblem | None:
    """Return why the first case whose comparison cannot be evaluated cannot be, or None.

    A semantic case can be evaluated only when the durable judge rotation has
    at least one judge. Whether those judges are authorized and available is
    checked once the runtime is loaded.
    """

    evaluator = OutcomeEvaluator()
    judges_configured = bool(repositories.judges.rotation().entries)

    for case in dataset.cases:
        if case.expected.comparison is OutcomeComparison.SEMANTIC:
            if not judges_configured:
                return ComparisonProblem(
                    message=(
                        f"Benchmark case {case.id} uses comparison 'semantic', "
                        "but no judges are configured."
                    ),
                    needs_judge=True,
                )

            continue

        try:
            evaluator.require_supported(
                case.expected.comparison,
                subject=f"Benchmark case {case.id}",
            )
        except UnsupportedComparisonError as exc:
            return ComparisonProblem(message=str(exc), needs_judge=False)

    return None


def undeclared_result(
    repositories: Repositories,
    workflow_ids: tuple[UUID, ...],
) -> str | None:
    """Return why the first configured workflow that declares no result cannot be judged.

    Unconfigured identifiers are left for the runtime to report.
    """

    for workflow_id in workflow_ids:
        specification = repositories.workflows.get(workflow_id)

        if specification is not None and specification.result is None:
            return f"Workflow {workflow_id} does not declare a result."

    return None


class Cancellable(Protocol):
    """What can ask a benchmark to stop: a `CancellationToken`."""

    @property
    def cancelled(
        self,
    ) -> bool:
        """Return whether the benchmark was asked to stop."""
        ...


ExecutedT = TypeVar("ExecutedT")
"""What an execution finishes with: a run's result, or a comparison's ranking."""

BenchmarkEventCallback = Callable[[BenchmarkEvent], None]
"""Receive one benchmark event, on the caller's thread; it must return quickly."""

BenchmarkRuntimeAccess = Callable[[Repositories], RuntimeEnvironment]
"""Compose the runtime a benchmark's cases run in, as a run's is."""


class _EventObserver:
    """Tell a callback each case as it starts and finishes, and stop between cases when asked.

    A callback that raises is not asked again, as a run's is not (ADR 0120),
    so a broken listener never stops the benchmark.
    """

    def __init__(
        self,
        on_event: BenchmarkEventCallback | None,
        cancel: Cancellable | None,
        total: int,
    ) -> None:
        """Tell `on_event` of each of `total` cases per workflow, stopping when `cancel` asks."""

        self._on_event = on_event
        self._cancel = cancel
        self._total = total
        self._started: dict[UUID, int] = {}
        self.finished: list[WorkflowBenchmarkCaseResult] = []

    def _emit(
        self,
        event: BenchmarkEvent,
    ) -> None:
        """Give one event to the callback, detaching a callback that raises."""

        if self._on_event is None:
            return

        try:
            self._on_event(event)
        except Exception:  # noqa: BLE001 - a listener never stops the benchmark
            self._on_event = None

    def case_started(
        self,
        case: BenchmarkCase,
        candidate: WorkflowCandidate,
    ) -> None:
        """Stop when asked to; otherwise tell that one case starts.

        Raises:
            RunCancelledError: The benchmark was asked to stop.
        """

        if self._cancel is not None and self._cancel.cancelled:
            raise RunCancelledError()

        workflow_id = candidate.metadata.id
        index = self._started.get(workflow_id, 0) + 1
        self._started[workflow_id] = index

        self._emit(
            CaseStarted(case_id=case.id, workflow_id=workflow_id, index=index, total=self._total)
        )

    def case_finished(
        self,
        result: WorkflowBenchmarkCaseResult,
        candidate: WorkflowCandidate,
    ) -> None:
        """Tell how one case went, keeping it in case the benchmark is cancelled."""

        self.finished.append(result)
        self._emit(
            CaseFinished(
                case_id=result.case_id,
                workflow_id=candidate.metadata.id,
                run_id=result.run.id,
                passed=result.evaluation.passed,
                score=result.evaluation.score,
            )
        )


def _keep_finished_runs(
    repositories: Repositories,
    observer: _EventObserver,
) -> None:
    """Keep the runs of the cases a cancelled benchmark finished, as any finished run is kept."""

    for result in observer.finished:
        repositories.runs.save(result.run)


def _recorder(
    repositories: Repositories,
) -> WorkflowBenchmarkEvidenceRecorder:
    """Return the recorder that saves a benchmark's runs, evaluations and execution."""

    return WorkflowBenchmarkEvidenceRecorder(
        runs=repositories.runs,
        evaluations=repositories.run_evaluations,
        executions=repositories.benchmark_executions,
    )


COMPARED_WORKFLOWS_MESSAGE: Final = "A comparison needs at least two distinct workflows."
"""What a comparison of fewer than two distinct workflows is refused with."""


def compared_workflows(
    workflow_ids: tuple[UUID, ...],
) -> None:
    """Refuse a comparison of fewer than two workflows, or of one workflow twice.

    Raises:
        InvalidArgumentError: Fewer than two distinct workflows are named.
    """

    if len(workflow_ids) < 2 or len(workflow_ids) != len(set(workflow_ids)):
        raise InvalidArgumentError(COMPARED_WORKFLOWS_MESSAGE)


def scoring_policy(
    target_latency_seconds: float,
    target_cost_usd: float,
) -> WorkflowScoringPolicy:
    """Return the policy that scores latency and cost against these targets.

    Raises:
        InvalidArgumentError: A target is not above zero, said as the policy says it.
    """

    try:
        return WorkflowScoringPolicy(
            target_latency_seconds=target_latency_seconds,
            target_cost_usd=target_cost_usd,
        )
    except ValidationError as exc:
        raise InvalidArgumentError(
            str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
        ) from exc


def checked_dataset(
    repositories: Repositories,
    benchmark_id: UUID,
    workflow_ids: tuple[UUID, ...],
) -> BenchmarkDataset:
    """Return a benchmark's latest dataset, refusing one that cannot run before any case does.

    Raises:
        NotFoundError: No benchmark has this ID.
        InvalidArgumentError: It has no cases, a comparison cannot be
            evaluated, or a workflow declares no result.
        JudgeUnavailableError: A semantic case has no judge to judge it.
    """

    dataset = repositories.benchmarks.get(benchmark_id)

    if dataset is None:
        raise NotFoundError(f"Benchmark dataset {benchmark_id} is not configured.")

    empty = missing_cases(dataset)

    if empty is not None:
        raise InvalidArgumentError(empty)

    problem = unsupported_comparison(repositories, dataset)

    if problem is not None:
        if problem.needs_judge:
            raise JudgeUnavailableError(problem.message)

        raise InvalidArgumentError(problem.message)

    undeclared = undeclared_result(repositories, workflow_ids)

    if undeclared is not None:
        raise InvalidArgumentError(undeclared)

    return dataset


async def refused(
    execution: Coroutine[Any, Any, ExecutedT],
) -> ExecutedT:
    """Await an execution, turning what refuses it into the service API's errors.

    Raises:
        NotFoundError: A workflow is not configured.
        RunNotStartedError: A workflow cannot be generated.
        JudgeUnavailableError: A judge cannot be used, or failed.
        InvalidArgumentError: A comparison has no evaluator.
        WorkflowResultMissingError: A run did not produce its declared result.
    """

    try:
        return await execution
    except WorkflowNotConfiguredError as exc:
        raise NotFoundError(str(exc)) from exc
    except WorkflowGenerationError as exc:
        raise RunNotStartedError(str(exc)) from exc
    except (RuntimeJudgeUnavailableError, SemanticJudgingError) as exc:
        raise JudgeUnavailableError(str(exc)) from exc
    except UnsupportedComparisonError as exc:
        raise InvalidArgumentError(str(exc)) from exc
    except WorkflowResultError as exc:
        raise WorkflowResultMissingError(str(exc)) from exc


def run_benchmark(
    repositories: Repositories,
    runtime: BenchmarkRuntimeAccess,
    benchmark_id: UUID,
    workflow_id: UUID,
    *,
    on_event: BenchmarkEventCallback | None = None,
    cancel: Cancellable | None = None,
) -> UUID:
    """Run one configured workflow against a benchmark's latest revision, and save it.

    Every case's run, every evaluation and the execution are saved, and the
    execution's ID returned. A cancelled benchmark keeps the case runs it
    finished and records no execution (ADR 0130).

    Raises:
        RunCancelledError: It was asked to stop.
        NotFoundError: No benchmark or workflow has the ID.
        InvalidArgumentError: The benchmark cannot run, as `benchmark run`
            refuses it.
        JudgeUnavailableError: A semantic case has no usable judge.
        RunNotStartedError: The workflow cannot be generated.
        WorkflowResultMissingError: A run did not produce its declared result.
    """

    if cancel is not None and cancel.cancelled:
        raise RunCancelledError()

    dataset = checked_dataset(repositories, benchmark_id, (workflow_id,))
    observer = _EventObserver(on_event, cancel, len(dataset.cases))

    try:
        result = asyncio.run(
            refused(
                execute_configured_benchmark(
                    runtime=runtime(repositories),
                    workflow_id=workflow_id,
                    dataset=dataset,
                    recorder=_recorder(repositories),
                    workflow_runner=case_runner(repositories),
                    observer=observer,
                )
            )
        )
    except RunCancelledError:
        _keep_finished_runs(repositories, observer)
        raise

    return result.id


def compare_benchmark(
    repositories: Repositories,
    runtime: BenchmarkRuntimeAccess,
    benchmark_id: UUID,
    workflow_ids: tuple[UUID, ...],
    *,
    target_latency_seconds: float,
    target_cost_usd: float,
    on_event: BenchmarkEventCallback | None = None,
    cancel: Cancellable | None = None,
) -> UUID:
    """Compare configured workflows against a benchmark's latest revision, and save it ranked.

    As `run_benchmark`, for two distinct workflows or more, each scored
    against the targets given.

    Raises:
        RunCancelledError: It was asked to stop.
        NotFoundError: No benchmark or workflow has the ID.
        InvalidArgumentError: Fewer than two distinct workflows, targets that
            are not positive, or a benchmark that cannot run.
        JudgeUnavailableError: A semantic case has no usable judge.
        RunNotStartedError: A workflow cannot be generated.
        WorkflowResultMissingError: A run did not produce its declared result.
    """

    if cancel is not None and cancel.cancelled:
        raise RunCancelledError()

    compared_workflows(workflow_ids)
    policy = scoring_policy(target_latency_seconds, target_cost_usd)
    dataset = checked_dataset(repositories, benchmark_id, workflow_ids)
    observer = _EventObserver(on_event, cancel, len(dataset.cases))

    try:
        ranking = asyncio.run(
            refused(
                compare_configured_benchmarks(
                    runtime=runtime(repositories),
                    workflow_ids=workflow_ids,
                    dataset=dataset,
                    scoring_policy=policy,
                    recorder=_recorder(repositories),
                    workflow_runner=case_runner(repositories),
                    observer=observer,
                )
            )
        )
    except RunCancelledError:
        _keep_finished_runs(repositories, observer)
        raise

    return ranking.id


__all__ = [
    "COMPARED_WORKFLOWS_MESSAGE",
    "BenchmarkEventCallback",
    "checked_dataset",
    "compared_workflows",
    "scoring_policy",
    "refused",
    "BenchmarkRuntimeAccess",
    "Cancellable",
    "ComparisonProblem",
    "compare_benchmark",
    "run_benchmark",
    "case_runner",
    "compare_configured_benchmarks",
    "execute_configured_benchmark",
    "judged_sensitivity",
    "missing_cases",
    "undeclared_result",
    "unsupported_comparison",
]
