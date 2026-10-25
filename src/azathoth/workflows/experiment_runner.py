"""Workflow experiment orchestration."""

from collections.abc import Callable

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeEvaluator,
)
from azathoth.revisions import content_digest
from azathoth.workflows.benchmark import (
    WorkflowBenchmarkResult,
    WorkflowBenchmarkRunner,
)
from azathoth.workflows.candidate import (
    WorkflowCandidate,
)
from azathoth.workflows.experiment import (
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
)
from azathoth.workflows.experiment_record import (
    WorkflowExperimentCaseObservation,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
)
from azathoth.workflows.experiment_recorder import (
    WorkflowExperimentEvidenceRecorder,
)
from azathoth.workflows.ranker import (
    WorkflowRanker,
)
from azathoth.workflows.result import (
    WorkflowResultError,
)
from azathoth.workflows.run_evaluation import (
    WorkflowRunEvaluation,
)
from azathoth.workflows.runner import (
    WorkflowRunner,
)
from azathoth.workflows.scorecard import (
    WorkflowScorecard,
)
from azathoth.workflows.scoring import (
    WorkflowScorer,
    aggregate_workflow_scorecards,
)


class WorkflowExperimentRunner:
    """Execute, evaluate, score, and rank workflow candidates over a benchmark.

    Every candidate runs every benchmark case. Each case judges the candidate's
    declared result with the case's own comparison, and the per-case
    scorecards are averaged into one scorecard per candidate for ranking.

    When a recorder is supplied, every candidate run, every evaluation, and
    one experiment record are persisted as durable evidence. Without one, the
    runner keeps no evidence beyond the returned result.
    """

    def __init__(
        self,
        *,
        scorer: WorkflowScorer,
        runner: WorkflowRunner | None = None,
        evaluator: OutcomeEvaluator | None = None,
        ranker: WorkflowRanker | None = None,
        recorder: WorkflowExperimentEvidenceRecorder | None = None,
    ) -> None:
        self._evaluator = evaluator if evaluator is not None else OutcomeEvaluator()
        self._benchmark_runner = WorkflowBenchmarkRunner(
            runner=runner if runner is not None else WorkflowRunner(),
            evaluator=self._evaluator,
        )
        self._scorer = scorer
        self._ranker = ranker if ranker is not None else WorkflowRanker()
        self._recorder = recorder

    async def run(
        self,
        *,
        workflows: tuple[WorkflowCandidate, ...],
        dataset: BenchmarkDataset,
    ) -> WorkflowExperimentResult:
        """Execute every candidate against every benchmark case and rank them.

        The dataset must contain cases, every case comparison must be
        supported, and every candidate must declare a result, all checked
        before any candidate executes. Failed runs are recorded and scored as
        failed cases rather than discarded, so a generation in which every run
        failed still ranks and records normally.

        Raises:
            ValueError: The dataset contains no cases.
            UnsupportedComparisonError: A case uses a comparison with no
                evaluator.
            WorkflowResultError: A candidate declares no result, or a
                successful run did not produce its declared result exactly
                once.
        """

        if not dataset.cases:
            raise ValueError(f"Benchmark {dataset.id} has no cases.")

        for case in dataset.cases:
            self._evaluator.require_supported(
                case.expected.comparison,
                subject=f"Benchmark case {case.id}",
            )

        for workflow in workflows:
            _require_declared_result(workflow)

        evidence: list[WorkflowExperimentEvidence] = []
        benchmarks: list[WorkflowBenchmarkResult] = []

        for workflow in workflows:
            benchmark = await self._benchmark_runner.run(
                dataset,
                _every_case(workflow),
            )

            if self._recorder is not None:
                for case_result in benchmark.cases:
                    self._recorder.runs.save(case_result.run)
                    self._recorder.evaluations.save(
                        WorkflowRunEvaluation(
                            run_id=case_result.run.id,
                            evaluation=case_result.evaluation,
                        )
                    )

            evidence.append(
                WorkflowExperimentEvidence(
                    candidate_signature=workflow.signature,
                    scorecard=self._score(benchmark),
                    judge_calls=benchmark.judge_calls,
                    judge_cost_usd=benchmark.judge_cost_usd,
                )
            )
            benchmarks.append(benchmark)

        scorecards = tuple(observation.scorecard for observation in evidence)

        ranking = self._ranker.rank(
            scorecards,
        )

        result = WorkflowExperimentResult(
            evidence=tuple(evidence),
            ranking=ranking,
        )

        if self._recorder is not None:
            self._recorder.experiments.save(
                self._record(
                    result=result,
                    dataset=dataset,
                    workflows=workflows,
                    benchmarks=tuple(benchmarks),
                )
            )

        return result

    def _score(
        self,
        benchmark: WorkflowBenchmarkResult,
    ) -> WorkflowScorecard:
        """Combine one candidate's per-case scorecards into one scorecard."""

        return aggregate_workflow_scorecards(
            tuple(
                self._scorer.score(
                    run=case.run,
                    evaluation=case.evaluation,
                )
                for case in benchmark.cases
            ),
            rationale=(f"Benchmark aggregate across {len(benchmark.cases)} cases."),
        )

    @staticmethod
    def _record(
        *,
        result: WorkflowExperimentResult,
        dataset: BenchmarkDataset,
        workflows: tuple[WorkflowCandidate, ...],
        benchmarks: tuple[WorkflowBenchmarkResult, ...],
    ) -> WorkflowExperimentRecord:
        """Build the durable record sharing the experiment result's identity.

        Observations keep candidate order, each holding one case per benchmark
        case in dataset order. Ranking entries are matched to evidence
        positions the same way the result orders its evidence, so the record's
        observation ranking agrees with the result's ranked evidence.
        """

        observations = tuple(
            WorkflowExperimentObservation(
                workflow=workflow.metadata,
                candidate_signature=entry.candidate_signature,
                cases=tuple(
                    WorkflowExperimentCaseObservation(
                        case_id=case.case_id,
                        run_id=case.run.id,
                        evaluation_id=case.evaluation.id,
                        passed=case.evaluation.passed,
                    )
                    for case in benchmark.cases
                ),
                scorecard=entry.scorecard,
            )
            for entry, workflow, benchmark in zip(
                result.evidence,
                workflows,
                benchmarks,
                strict=True,
            )
        )

        remaining = list(range(len(result.evidence)))
        ranking: list[int] = []

        for ranked in result.ranking.entries:
            position = next(
                index for index in remaining if result.evidence[index].scorecard == ranked.scorecard
            )

            remaining.remove(position)
            ranking.append(position)

        return WorkflowExperimentRecord(
            id=result.id,
            benchmark_id=dataset.id,
            benchmark_digest=content_digest(dataset),
            observations=observations,
            ranking=tuple(observations[index].id for index in ranking),
        )


def _every_case(
    workflow: WorkflowCandidate,
) -> Callable[[BenchmarkCase], WorkflowCandidate]:
    """Return a candidate factory that runs one candidate for every case."""

    def factory(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return workflow

    return factory


def _require_declared_result(
    workflow: WorkflowCandidate,
) -> None:
    """Reject an experiment candidate that declares no result.

    Raises:
        WorkflowResultError: The candidate declares no result.
    """

    if workflow.result is None:
        raise WorkflowResultError(f"Workflow {workflow.metadata.id} does not declare a result.")
