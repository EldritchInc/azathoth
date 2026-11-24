"""A benchmark's saved runs and comparisons as the service API shows them (ADR 0130).

An execution records the content digest of the benchmark it ran, not its
revision number, so the revision is told from the benchmark's history: the
latest revision holding that content.
"""

from collections.abc import Mapping, Sequence
from uuid import UUID

from azathoth.api.models import (
    BenchmarkExecutionDetail,
    BenchmarkExecutionSummary,
    CandidateScorecard,
    ComparisonTally,
    ExecutionCandidate,
    ExecutionCandidateSummary,
    ExecutionCaseResult,
    ScoringPolicySummary,
)
from azathoth.evaluation import BenchmarkDatasetRevision
from azathoth.sensitivity import effective_sensitivity
from azathoth.workflows import (
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionCase,
    WorkflowBenchmarkExecutionRecord,
    WorkflowRun,
    WorkflowRunEvaluation,
)


def execution_not_found_message(
    execution_id: UUID,
) -> str:
    """Return what an execution that was never saved is refused with."""

    return f"Benchmark execution {execution_id} was not found."


def benchmark_revision(
    history: Sequence[BenchmarkDatasetRevision],
    execution: WorkflowBenchmarkExecutionRecord,
) -> int | None:
    """Return the number of the benchmark revision an execution ran, when it can be told.

    It is the latest revision with the content the execution names: a
    revision that returned to earlier content ran as that content did.
    """

    if execution.benchmark_digest is None:
        return None

    matching = [
        revision for revision in history if revision.content_digest == execution.benchmark_digest
    ]

    return matching[-1].number if matching else None


def _candidate_summary(
    candidate: WorkflowBenchmarkExecutionCandidate,
) -> ExecutionCandidateSummary:
    """Return what a list of executions shows of one workflow an execution ran."""

    return ExecutionCandidateSummary(
        candidate_id=candidate.id,
        workflow_id=candidate.workflow.id,
        workflow_name=candidate.workflow.name,
        workflow_revision=candidate.candidate_signature.workflow_revision,
        cases_run=candidate.cases_run,
        cases_passed=candidate.cases_passed,
        accuracy=candidate.accuracy,
        overall_score=None if candidate.scorecard is None else candidate.scorecard.overall_score,
    )


def _case_result(
    case: WorkflowBenchmarkExecutionCase,
    evaluations: Mapping[UUID, WorkflowRunEvaluation],
) -> ExecutionCaseResult:
    """Return how one case went, with its evaluation's score and reason while it is kept."""

    evaluation = evaluations.get(case.evaluation_id)

    return ExecutionCaseResult(
        case_id=case.case_id,
        comparison=case.comparison.value,
        run_id=case.run_id,
        evaluation_id=case.evaluation_id,
        passed=case.passed,
        run_failure=case.run_failure,
        score=None if evaluation is None else evaluation.evaluation.score,
        reason=None if evaluation is None else evaluation.evaluation.reason,
        judge_calls=case.judge_calls,
        judge_cost_usd=case.judge_cost_usd,
    )


def _totals(
    candidate: WorkflowBenchmarkExecutionCandidate,
    runs: Mapping[UUID, WorkflowRun],
) -> tuple[int, int, float] | None:
    """Return the tokens, latency and cost a workflow's case runs measured, as a run sums them.

    They are summed case by case and step by step, as `benchmark run`
    totals them. None is returned once any of the runs is not kept.
    """

    kept = [runs.get(case.run_id) for case in candidate.cases]

    if any(run is None for run in kept):
        return None

    measured = [
        step.execution.metrics
        for run in kept
        if run is not None
        for step in run.steps
        if step.execution is not None
        if step.execution.metrics is not None
    ]

    return (
        sum(metrics.total_tokens for metrics in measured if metrics.total_tokens is not None),
        sum(metrics.latency_ms for metrics in measured if metrics.latency_ms is not None),
        sum(
            metrics.estimated_cost_usd
            for metrics in measured
            if metrics.estimated_cost_usd is not None
        ),
    )


def _candidate(
    candidate: WorkflowBenchmarkExecutionCandidate,
    evaluations: Mapping[UUID, WorkflowRunEvaluation],
    runs: Mapping[UUID, WorkflowRun],
) -> ExecutionCandidate:
    """Return one workflow an execution ran, with every case."""

    scorecard = candidate.scorecard
    totals = _totals(candidate, runs)

    return ExecutionCandidate(
        **_candidate_summary(candidate).model_dump(),
        total_tokens=None if totals is None else totals[0],
        total_latency_ms=None if totals is None else totals[1],
        total_cost_usd=None if totals is None else totals[2],
        strategy_ids=candidate.candidate_signature.strategy_ids,
        run_failures=candidate.run_failures,
        judged_semantically=candidate.judged_semantically,
        judge_calls=candidate.judge_calls,
        judge_cost_usd=candidate.judge_cost_usd,
        tallies=tuple(
            ComparisonTally(
                comparison=tally.comparison.value,
                cases_run=tally.cases_run,
                cases_passed=tally.cases_passed,
            )
            for tally in candidate.comparison_tallies
        ),
        scorecard=(
            None
            if scorecard is None
            else CandidateScorecard(
                quality_score=scorecard.quality_score,
                reliability_score=scorecard.reliability_score,
                latency_score=scorecard.latency_score,
                cost_score=scorecard.cost_score,
                citation_score=scorecard.citation_score,
                overall_score=scorecard.overall_score,
                rationale=scorecard.rationale,
            )
        ),
        cases=tuple(_case_result(case, evaluations) for case in candidate.cases),
    )


def _command(
    execution: WorkflowBenchmarkExecutionRecord,
) -> str:
    """Return the command that shows one execution."""

    return f"azathoth benchmark execution-show {execution.id}"


def execution_summary(
    execution: WorkflowBenchmarkExecutionRecord,
    *,
    revision: int | None = None,
) -> BenchmarkExecutionSummary:
    """Return what a list of a benchmark's executions shows of one."""

    return BenchmarkExecutionSummary(
        execution_id=execution.id,
        benchmark_id=execution.benchmark_id,
        benchmark_revision=revision,
        benchmark_digest=execution.benchmark_digest,
        kind=execution.kind.value,
        recorded_at=execution.recorded_at,
        sensitivity=effective_sensitivity(execution.sensitivity),
        case_count=len(execution.case_ids),
        candidates=tuple(
            _candidate_summary(candidate) for candidate in execution.ranked_candidates
        ),
        command=_command(execution),
    )


def execution_detail(
    execution: WorkflowBenchmarkExecutionRecord,
    *,
    revision: int | None = None,
    evaluations: Mapping[UUID, WorkflowRunEvaluation] | None = None,
    runs: Mapping[UUID, WorkflowRun] | None = None,
) -> BenchmarkExecutionDetail:
    """Return one execution with every workflow it ran, best first, and every case.

    A case's score and reason are its evaluation's, among `evaluations`,
    and a workflow's totals are those its case runs among `runs` measured.
    """

    kept = {} if evaluations is None else evaluations
    ran = {} if runs is None else runs
    policy = execution.scoring_policy

    return BenchmarkExecutionDetail(
        execution_id=execution.id,
        benchmark_id=execution.benchmark_id,
        benchmark_revision=revision,
        benchmark_digest=execution.benchmark_digest,
        kind=execution.kind.value,
        recorded_at=execution.recorded_at,
        sensitivity=effective_sensitivity(execution.sensitivity),
        case_count=len(execution.case_ids),
        scoring_policy=(
            None
            if policy is None
            else ScoringPolicySummary(
                target_latency_seconds=policy.target_latency_seconds,
                target_cost_usd=policy.target_cost_usd,
            )
        ),
        candidates=tuple(
            _candidate(candidate, kept, ran) for candidate in execution.ranked_candidates
        ),
        command=_command(execution),
    )


__all__ = [
    "benchmark_revision",
    "execution_detail",
    "execution_not_found_message",
    "execution_summary",
]
