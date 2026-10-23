"""Durable recording of workflow benchmark execution evidence."""

from collections.abc import Mapping
from dataclasses import dataclass

from azathoth.workflows.benchmark import (
    WorkflowBenchmarkComparison,
    WorkflowBenchmarkRanking,
    WorkflowBenchmarkResult,
)
from azathoth.workflows.benchmark_execution_repository import (
    WorkflowBenchmarkExecutionRepository,
)
from azathoth.workflows.benchmark_record import (
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionCase,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkExecutionRecord,
)
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.run_evaluation import WorkflowRunEvaluation
from azathoth.workflows.run_evaluation_repository import WorkflowRunEvaluationRepository
from azathoth.workflows.run_repository import WorkflowRunRepository
from azathoth.workflows.scorecard import WorkflowScorecard
from azathoth.workflows.scoring import WorkflowScoringPolicy


@dataclass(frozen=True)
class WorkflowBenchmarkEvidenceRecorder:
    """Group the repositories that receive durable benchmark evidence.

    Every case run is saved, including failed runs, and every case evaluation
    is saved with its judge calls. Each completed run or comparison is then
    saved as one execution record referencing those runs and evaluations.

    The record is built and validated before anything is saved, so evidence
    that cannot form a valid record leaves every repository unchanged.
    """

    runs: WorkflowRunRepository
    evaluations: WorkflowRunEvaluationRepository
    executions: WorkflowBenchmarkExecutionRepository

    def record_run(
        self,
        result: WorkflowBenchmarkResult,
        *,
        candidate: WorkflowCandidate,
    ) -> WorkflowBenchmarkExecutionRecord:
        """Save one benchmark run and return its execution record.

        The record shares the result's identity.

        Raises:
            ValueError: The result has no cases, or its runs were not produced
                by the candidate's workflow.
        """

        record = WorkflowBenchmarkExecutionRecord(
            id=result.id,
            benchmark_id=result.dataset_id,
            benchmark_digest=result.dataset_digest,
            kind=WorkflowBenchmarkExecutionKind.RUN,
            candidates=(
                _execution_candidate(
                    result,
                    candidate=candidate,
                    scorecard=None,
                ),
            ),
        )

        self._save_case_evidence(result)
        self.executions.save(record)

        return record

    def record_comparison(
        self,
        comparison: WorkflowBenchmarkComparison,
        ranking: WorkflowBenchmarkRanking,
        *,
        candidates: Mapping[str, WorkflowCandidate],
        scoring_policy: WorkflowScoringPolicy,
    ) -> WorkflowBenchmarkExecutionRecord:
        """Save one benchmark comparison and return its execution record.

        Candidates are keyed by comparison name. The record shares the
        ranking's identity, keeps comparison order for its candidates, and
        ranks them in the ranking's order.

        Raises:
            ValueError: The ranking does not rank every compared candidate
                exactly once, a compared candidate has no workflow candidate,
                or a candidate's runs were not produced by its workflow.
        """

        names = tuple(entry.name for entry in comparison.candidates)
        ranked_names = tuple(entry.name for entry in ranking.entries)

        if len(ranked_names) != len(set(ranked_names)) or set(ranked_names) != set(names):
            raise ValueError("Benchmark ranking must rank every compared candidate exactly once.")

        for name in names:
            if name not in candidates:
                raise ValueError(
                    f"Benchmark comparison candidate {name!r} has no workflow candidate."
                )

        scorecards = {entry.name: entry.scorecard for entry in ranking.entries}

        execution_candidates = {
            entry.name: _execution_candidate(
                entry.result,
                candidate=candidates[entry.name],
                scorecard=scorecards[entry.name],
            )
            for entry in comparison.candidates
        }

        record = WorkflowBenchmarkExecutionRecord(
            id=ranking.id,
            benchmark_id=comparison.dataset_id,
            benchmark_digest=comparison.dataset_digest,
            kind=WorkflowBenchmarkExecutionKind.COMPARE,
            candidates=tuple(execution_candidates[name] for name in names),
            ranking=tuple(execution_candidates[name].id for name in ranked_names),
            scoring_policy=scoring_policy,
        )

        for entry in comparison.candidates:
            self._save_case_evidence(entry.result)

        self.executions.save(record)

        return record

    def _save_case_evidence(
        self,
        result: WorkflowBenchmarkResult,
    ) -> None:
        """Save every case run and its evaluation."""

        for case in result.cases:
            self.runs.save(case.run)
            self.evaluations.save(
                WorkflowRunEvaluation(
                    run_id=case.run.id,
                    evaluation=case.evaluation,
                )
            )


def _execution_candidate(
    result: WorkflowBenchmarkResult,
    *,
    candidate: WorkflowCandidate,
    scorecard: WorkflowScorecard | None,
) -> WorkflowBenchmarkExecutionCandidate:
    """Return the durable evidence of one candidate across its benchmark cases.

    Raises:
        ValueError: The result has no cases, or its runs were not produced by
            the candidate's workflow.
    """

    if not result.cases:
        raise ValueError(f"Benchmark result {result.id} has no cases to record.")

    for case in result.cases:
        if case.run.workflow.id != candidate.metadata.id:
            raise ValueError(
                f"Benchmark case {case.case_id} was not run by workflow {candidate.metadata.id}."
            )

    return WorkflowBenchmarkExecutionCandidate(
        workflow=candidate.metadata,
        candidate_signature=candidate.signature,
        cases=tuple(
            WorkflowBenchmarkExecutionCase(
                case_id=case.case_id,
                comparison=case.comparison,
                run_id=case.run.id,
                evaluation_id=case.evaluation.id,
                passed=case.evaluation.passed,
                run_failure=case.run_failure,
                judge_calls=case.judge_calls,
                judge_cost_usd=case.judge_cost_usd,
            )
            for case in result.cases
        ),
        scorecard=scorecard,
    )


__all__ = [
    "WorkflowBenchmarkEvidenceRecorder",
]
