"""Optimizing a configured workflow against a benchmark (ADRs 0051, 0072 and 0131).

The service API's `optimization.optimize` and the command line's `workflow
optimize` optimize through `optimize_configured_workflow`, as benchmarks
share their execution (ADR 0130), so the two cannot come to optimize
differently. The API's call checks everything before any candidate runs,
tells each generation and candidate as it goes, and stops between
candidates when cancelled, keeping every experiment it finished.
"""

import asyncio
from collections.abc import Callable
from uuid import UUID

from azathoth.api.benchmark_execution import (
    BenchmarkRuntimeAccess,
    Cancellable,
    case_runner,
    checked_dataset,
    judged_sensitivity,
    refused,
    scoring_policy,
    undeclared_result,
)
from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.errors import (
    InvalidArgumentError,
    RunCancelledError,
    WorkflowResultMissingError,
)
from azathoth.api.experiments import experiment_command
from azathoth.api.models import (
    CandidateFinished,
    CandidateScorecard,
    GenerationFinished,
    GenerationStarted,
    OptimizationEvent,
    OptimizationExperiment,
    OptimizationGeneration,
    OptimizationSummary,
    OptimizedStep,
)
from azathoth.evaluation import BenchmarkDataset, OutcomeComparison
from azathoth.optimization import (
    ModelSubstitutionWorkflowOptimizer,
    WorkflowOptimizationResult,
    WorkflowOptimizationSession,
    WorkflowOptimizationSessionRunner,
    WorkflowOptimizer,
    resolve_workflow_experiment_winner,
)
from azathoth.persistence.repositories import Repositories
from azathoth.prompting import ContextPromptStrategy, PromptStrategy
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowBenchmarkResult,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowExperimentEvidence,
    WorkflowExperimentEvidenceRecorder,
    WorkflowExperimentResult,
    WorkflowExperimentRunner,
    WorkflowResultError,
    WorkflowRunner,
    WorkflowScorer,
    WorkflowScoringPolicy,
)

OptimizationEventCallback = Callable[[OptimizationEvent], None]
"""Receive one optimization event, on the caller's thread; it must return quickly."""

GENERATIONS_MESSAGE = "An optimization session needs at least one generation."


class _Teller:
    """Tell a callback each event, and stop between candidates when asked.

    A callback that raises is not asked again, as a run's is not (ADR 0120),
    so a broken listener never stops the session.
    """

    def __init__(
        self,
        on_event: OptimizationEventCallback | None,
        cancel: Cancellable | None,
    ) -> None:
        """Tell `on_event` of every event, stopping when `cancel` asks."""

        self._on_event = on_event
        self._cancel = cancel

    def tell(
        self,
        event: OptimizationEvent,
    ) -> None:
        """Give one event to the callback, detaching a callback that raises."""

        if self._on_event is None:
            return

        try:
            self._on_event(event)
        except Exception:  # noqa: BLE001 - a listener never stops the session
            self._on_event = None

    def check(
        self,
    ) -> None:
        """Stop when asked to.

        Raises:
            RunCancelledError: The session was asked to stop.
        """

        if self._cancel is not None and self._cancel.cancelled:
            raise RunCancelledError()


class _CandidateTeller:
    """Tell each candidate of one generation as it finishes, stopping before the next."""

    def __init__(
        self,
        teller: _Teller,
        generation: int,
    ) -> None:
        """Tell candidates of `generation` through `teller`."""

        self._teller = teller
        self._generation = generation

    def candidate_starting(
        self,
        candidate: WorkflowCandidate,
    ) -> None:
        """Stop when asked to, before another candidate runs.

        Raises:
            RunCancelledError: The session was asked to stop.
        """

        del candidate
        self._teller.check()

    def candidate_finished(
        self,
        candidate: WorkflowCandidate,
        evidence: WorkflowExperimentEvidence,
        benchmark: WorkflowBenchmarkResult,
    ) -> None:
        """Tell how one candidate did."""

        self._teller.tell(
            CandidateFinished(
                generation=self._generation,
                workflow_id=candidate.metadata.id,
                strategy_ids=candidate.signature.strategy_ids,
                cases_run=len(benchmark.cases),
                cases_passed=sum(case.evaluation.passed for case in benchmark.cases),
                overall_score=evidence.scorecard.overall_score,
            )
        )


def _finished(
    generation: int,
    experiment: WorkflowExperimentResult,
    proposed: int,
) -> GenerationFinished:
    """Return the event that tells one generation's experiment and winner."""

    winner = experiment.winner_evidence

    return GenerationFinished(
        generation=generation,
        experiment_id=experiment.id,
        winner_strategy_ids=winner.candidate_signature.strategy_ids,
        winner_score=winner.scorecard.overall_score,
        proposed=proposed,
    )


class _ToldExperiments:
    """Run each generation's experiment, telling it as it starts and each candidate as it ends.

    The experiment after the last generation is the final evaluation, told
    as one more generation that proposes nothing.
    """

    def __init__(
        self,
        runner: WorkflowExperimentRunner,
        teller: _Teller,
        max_generations: int,
    ) -> None:
        """Run experiments with `runner`, telling `teller`, for `max_generations` generations."""

        self._runner = runner
        self._teller = teller
        self._max_generations = max_generations
        self._generation = 0

    async def run(
        self,
        *,
        workflows: tuple[WorkflowCandidate, ...],
        dataset: BenchmarkDataset,
    ) -> WorkflowExperimentResult:
        """Run one generation's experiment, telling it."""

        self._generation += 1
        final = self._generation > self._max_generations

        self._teller.check()
        self._teller.tell(
            GenerationStarted(generation=self._generation, candidates=len(workflows), final=final)
        )

        experiment = await self._runner.run(
            workflows=workflows,
            dataset=dataset,
            observer=_CandidateTeller(self._teller, self._generation),
        )

        if final:
            self._teller.tell(_finished(self._generation, experiment, 0))

        return experiment


class _ToldOptimizer:
    """Propose each next population, telling the generation it ends."""

    def __init__(
        self,
        optimizer: WorkflowOptimizer,
        teller: _Teller,
    ) -> None:
        """Propose with `optimizer`, telling `teller`."""

        self._optimizer = optimizer
        self._teller = teller

    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult:
        """Propose the next population, and tell the generation it ends."""

        result = self._optimizer.optimize(
            experiment=experiment,
            candidates=candidates,
            generation=generation,
        )

        self._teller.tell(_finished(generation, experiment, len(result.candidates)))

        return result


async def optimize_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    dataset: BenchmarkDataset,
    scoring_policy: WorkflowScoringPolicy,
    max_generations: int,
    recorder: WorkflowExperimentEvidenceRecorder | None = None,
    workflow_runner: WorkflowRunner | None = None,
    on_event: OptimizationEventCallback | None = None,
    cancel: Cancellable | None = None,
) -> WorkflowOptimizationSession:
    """Run empirical model-substitution optimization for one workflow.

    Every generation runs each candidate against every benchmark case and
    judges the workflow's declared result with each case's own comparison. A
    workflow without a declared result, an empty benchmark, an unsupported
    comparison, and an unusable judge for a semantic case are all rejected
    before any candidate is generated or executed. Semantic cases are judged
    by the runtime's judge rotation; judge cost is recorded as evaluation
    evidence and never charged to a candidate.

    When a recorder is supplied, every generation's candidate runs,
    evaluations, and experiment record are persisted as durable evidence.
    Every candidate run runs in the given workflow runner (ADR 0117).

    `on_event` hears each generation start and end and each candidate
    finish, and `cancel` is checked before each candidate (ADR 0131).

    Raises:
        ValueError: The benchmark contains no cases.
        UnsupportedComparisonError: A benchmark case uses a comparison with
            no evaluator.
        WorkflowResultError: The configured workflow declares no result.
        JudgeUnavailableError: The benchmark has semantic cases and a judge
            cannot be used.
        RunCancelledError: `cancel` asked it to stop.
    """

    specification = runtime.workflows.get(
        workflow_id,
    )

    if specification is not None and specification.result is None:
        raise WorkflowResultError(f"Workflow {workflow_id} does not declare a result.")

    if not dataset.cases:
        raise ValueError(f"Benchmark {dataset.id} has no cases.")

    evaluator = runtime.outcome_evaluator(
        semantic=dataset.uses_comparison(OutcomeComparison.SEMANTIC),
        sensitivity=judged_sensitivity(dataset),
    )

    for case in dataset.cases:
        evaluator.require_supported(
            case.expected.comparison,
            subject=f"Benchmark case {case.id}",
        )

    initial_candidate = runtime.generate_workflow_candidate(
        workflow_id,
        sensitivity=dataset.sensitivity,
    )

    experiment_runner = WorkflowExperimentRunner(
        scorer=WorkflowScorer(
            policy=scoring_policy,
        ),
        runner=workflow_runner,
        evaluator=evaluator,
        recorder=recorder,
    )

    optimizer = ModelSubstitutionWorkflowOptimizer(
        workflows=runtime.workflows,
        models=runtime.models,
        portfolio=runtime.portfolio,
        registry=runtime.language_models,
        sensitivity=dataset.sensitivity,
    )

    if on_event is None and cancel is None:
        session_runner = WorkflowOptimizationSessionRunner(
            experiment_runner=experiment_runner,
            optimizer=optimizer,
        )
    else:
        teller = _Teller(on_event, cancel)
        session_runner = WorkflowOptimizationSessionRunner(
            experiment_runner=_ToldExperiments(experiment_runner, teller, max_generations),
            optimizer=_ToldOptimizer(optimizer, teller),
        )

    return await session_runner.run(
        initial_candidates=(initial_candidate,),
        dataset=dataset,
        max_generations=max_generations,
    )


def _optimized_step(
    step: WorkflowCandidateStep,
) -> OptimizedStep:
    """Return one step of a winning candidate: its strategy, and the model it is bound to."""

    strategy = step.strategy
    binding = (
        strategy.model_binding
        if isinstance(strategy, (PromptStrategy, ContextPromptStrategy))
        else None
    )

    return OptimizedStep(
        step_id=step.id,
        name=strategy.metadata.name,
        strategy_id=strategy.metadata.id,
        model=None if binding is None else binding.identifier,
    )


def _experiment(
    experiment: WorkflowExperimentResult,
    candidates: tuple[WorkflowCandidate, ...],
) -> OptimizationExperiment:
    """Return what one experiment of a session judged, among `candidates`, and its winner."""

    evidence = experiment.winner_evidence
    winner = resolve_workflow_experiment_winner(experiment=experiment, candidates=candidates)
    scorecard = evidence.scorecard

    return OptimizationExperiment(
        experiment_id=experiment.id,
        evaluated=len(experiment.evidence),
        judge_calls=experiment.judge_calls,
        judge_cost_usd=experiment.judge_cost_usd,
        winner_workflow_id=evidence.candidate_signature.workflow_id,
        winner_strategy_ids=evidence.candidate_signature.strategy_ids,
        winner_steps=tuple(_optimized_step(step) for step in winner.steps),
        winner_scorecard=CandidateScorecard(
            quality_score=scorecard.quality_score,
            reliability_score=scorecard.reliability_score,
            latency_score=scorecard.latency_score,
            cost_score=scorecard.cost_score,
            citation_score=scorecard.citation_score,
            overall_score=scorecard.overall_score,
            rationale=scorecard.rationale,
        ),
    )


def optimization_summary(
    session: WorkflowOptimizationSession,
    workflow_id: UUID,
    benchmark_id: UUID,
) -> OptimizationSummary:
    """Return what one session measured, with each experiment's winner as it was built.

    Each generation's experiment judged the population before it: the
    session's first candidates, and then what the generation before
    proposed. The final evaluation judged the last generation's proposals.
    """

    experiments = tuple(result.previous_experiment for result in session.generations)

    if session.final_experiment is not None:
        experiments = (*experiments, session.final_experiment)

    winning = session.winning_experiment

    assert winning is not None

    last = session.generations[-1].generation
    generations: list[OptimizationGeneration] = []
    evaluated = tuple(session.initial_candidates)

    for result in session.generations:
        measured = result.previous_experiment
        generations.append(
            OptimizationGeneration(
                generation=result.generation,
                experiment=_experiment(measured, evaluated),
                experiment_id=measured.id,
                winner_strategy_ids=measured.winner_evidence.candidate_signature.strategy_ids,
                winner_score=measured.winner_evidence.scorecard.overall_score,
                proposed=len(result.candidates),
            )
        )
        evaluated = tuple(result.candidates)

    return OptimizationSummary(
        workflow_id=workflow_id,
        workflow_name=session.initial_candidates[0].metadata.name,
        initial_candidates=len(session.initial_candidates),
        benchmark_id=benchmark_id,
        generations=tuple(generations),
        final_experiment_id=(
            session.final_experiment.id if session.final_experiment is not None else None
        ),
        final_experiment=(
            None
            if session.final_experiment is None
            else _experiment(session.final_experiment, session.final_population)
        ),
        final_skipped=(
            None
            if session.final_experiment is not None
            else (
                f"Generation {last} proposed no new candidates, "
                "so its winner is the session's winner."
            )
        ),
        winning_experiment_id=winning.id,
        judge_calls=sum(experiment.judge_calls for experiment in experiments),
        judge_cost_usd=sum(experiment.judge_cost_usd for experiment in experiments),
        command=experiment_command(winning.id),
    )


def optimize_workflow(
    repositories: Repositories,
    runtime: BenchmarkRuntimeAccess,
    workflow_id: UUID,
    benchmark_id: UUID,
    *,
    target_latency_seconds: float,
    target_cost_usd: float,
    generations: int = 1,
    on_event: OptimizationEventCallback | None = None,
    cancel: Cancellable | None = None,
) -> OptimizationSummary:
    """Optimize one configured workflow against a benchmark's latest revision, and record it.

    Raises:
        RunCancelledError: It was asked to stop.
        NotFoundError: No benchmark or workflow has the ID.
        InvalidArgumentError: Fewer than one generation, a target that is not
            above zero, or a benchmark that cannot run.
        WorkflowResultMissingError: The workflow declares no result.
        JudgeUnavailableError: A semantic case has no usable judge.
        RunNotStartedError: The workflow cannot be generated.
    """

    if cancel is not None and cancel.cancelled:
        raise RunCancelledError()

    if generations < 1:
        raise InvalidArgumentError(GENERATIONS_MESSAGE)

    policy = scoring_policy(target_latency_seconds, target_cost_usd)
    dataset = checked_dataset(repositories, benchmark_id, ())
    undeclared = undeclared_result(repositories, (workflow_id,))

    if undeclared is not None:
        raise WorkflowResultMissingError(undeclared)

    session = asyncio.run(
        refused(
            optimize_configured_workflow(
                runtime=runtime(repositories),
                workflow_id=workflow_id,
                dataset=dataset,
                scoring_policy=policy,
                max_generations=generations,
                recorder=WorkflowExperimentEvidenceRecorder(
                    runs=repositories.runs,
                    evaluations=repositories.run_evaluations,
                    experiments=repositories.experiments,
                ),
                workflow_runner=case_runner(repositories),
                on_event=on_event,
                cancel=cancel,
            )
        )
    )

    return optimization_summary(session, workflow_id, benchmark_id)


class Optimization:
    """Optimize an instance's workflows against its benchmarks (ADR 0131)."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        runtime: BenchmarkRuntimeAccess,
    ) -> None:
        """Optimize over `repositories`, running candidates in the runtime `runtime` composes."""

        self._repositories = repositories
        self._runtime = runtime

    def optimize(
        self,
        workflow_id: UUID,
        benchmark_id: UUID,
        *,
        target_latency_seconds: float,
        target_cost_usd: float,
        generations: int = 1,
        on_event: OptimizationEventCallback | None = None,
        cancel: Cancellable | None = None,
    ) -> OptimizationSummary:
        """Optimize one workflow against a benchmark's latest revision, as `workflow optimize`.

        Everything is checked before any candidate runs. `on_event` hears
        each generation start and finish and each candidate finish, on the
        caller's thread, and `cancel` is checked before each candidate: a
        cancelled session keeps every experiment it finished, and raises.
        Every experiment it names is recorded. It is the `optimize` action
        (ADR 0131).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark or workflow has the ID.
            InvalidArgumentError: Fewer than one generation, a target that is
                not above zero, a benchmark with no cases, or a comparison
                that cannot be evaluated.
            WorkflowResultMissingError: The workflow declares no result.
            JudgeUnavailableError: A semantic case has no usable judge, or a
                judge failed.
            RunNotStartedError: The workflow cannot be generated.
            RunCancelledError: `cancel` asked it to stop.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
        """

        return optimize_workflow(
            self._repositories(),
            self._runtime,
            workflow_id,
            benchmark_id,
            target_latency_seconds=target_latency_seconds,
            target_cost_usd=target_cost_usd,
            generations=generations,
            on_event=on_event,
            cancel=cancel,
        )


__all__ = [
    "GENERATIONS_MESSAGE",
    "Optimization",
    "OptimizationEventCallback",
    "optimization_summary",
    "optimize_configured_workflow",
    "optimize_workflow",
]
