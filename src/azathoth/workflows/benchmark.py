"""Execution and results for workflow benchmarks."""

from collections.abc import Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    EvaluationResult,
    ExactMatchEvaluator,
)
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.runner import WorkflowRunner


class WorkflowBenchmarkCaseResult(BaseModel):
    """Recorded benchmark evidence for one workflow execution."""

    model_config = ConfigDict(frozen=True)

    case_id: UUID
    run: WorkflowRun
    evaluation: EvaluationResult


class WorkflowBenchmarkResult(BaseModel):
    """Aggregate result of executing one benchmark dataset."""

    model_config = ConfigDict(frozen=True)

    dataset_id: UUID
    cases: tuple[WorkflowBenchmarkCaseResult, ...] = ()

    @property
    def cases_run(self) -> int:
        """Return the number of executed benchmark cases."""

        return len(self.cases)

    @property
    def cases_passed(self) -> int:
        """Return the number of benchmark cases that passed evaluation."""

        return sum(case.evaluation.passed for case in self.cases)

    @property
    def accuracy(self) -> float:
        """Return the fraction of benchmark cases that passed."""

        if not self.cases:
            return 0.0

        return self.cases_passed / self.cases_run

    @property
    def total_tokens(self) -> int:
        """Return total recorded token usage across benchmark executions."""

        return sum(
            metrics.total_tokens
            for case in self.cases
            for step in case.run.steps
            if step.execution is not None
            if step.execution.metrics is not None
            if (metrics := step.execution.metrics).total_tokens is not None
        )

    @property
    def total_cost_usd(self) -> float:
        """Return total recorded model cost across benchmark executions."""

        return sum(
            metrics.estimated_cost_usd
            for case in self.cases
            for step in case.run.steps
            if step.execution is not None
            if step.execution.metrics is not None
            if (metrics := step.execution.metrics).estimated_cost_usd is not None
        )

    @property
    def total_latency_ms(self) -> int:
        """Return total recorded provider latency across benchmark executions."""

        return sum(
            metrics.latency_ms
            for case in self.cases
            for step in case.run.steps
            if step.execution is not None
            if step.execution.metrics is not None
            if (metrics := step.execution.metrics).latency_ms is not None
        )


class WorkflowBenchmarkRunner:
    """Execute workflow candidates across durable benchmark datasets."""

    def __init__(
        self,
        runner: WorkflowRunner | None = None,
        evaluator: ExactMatchEvaluator | None = None,
    ) -> None:
        self._runner = runner if runner is not None else WorkflowRunner()
        self._evaluator = evaluator if evaluator is not None else ExactMatchEvaluator()

    async def run(
        self,
        dataset: BenchmarkDataset,
        candidate_factory: Callable[[BenchmarkCase], WorkflowCandidate],
        *,
        output_name: str,
    ) -> WorkflowBenchmarkResult:
        """Execute and evaluate every case in a benchmark dataset."""

        results: list[WorkflowBenchmarkCaseResult] = []

        for case in dataset.cases:
            candidate = candidate_factory(case)

            run = await self._runner.run(
                candidate,
                Context(),
            )

            values = run.values_named(output_name)

            if len(values) != 1:
                raise ValueError(
                    f"Benchmark workflow must produce exactly one value named {output_name!r}."
                )

            evaluation = await self._evaluator.evaluate(
                case.expected,
                values[0].value,
            )

            results.append(
                WorkflowBenchmarkCaseResult(
                    case_id=case.id,
                    run=run,
                    evaluation=evaluation,
                )
            )

        return WorkflowBenchmarkResult(
            dataset_id=dataset.id,
            cases=tuple(results),
        )
