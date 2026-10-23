"""Deterministic in-memory persistence for benchmark execution records."""

from uuid import UUID

from azathoth.workflows.benchmark_execution_repository import (
    WorkflowBenchmarkExecutionRepository,
)
from azathoth.workflows.benchmark_record import (
    WorkflowBenchmarkExecutionRecord,
)


class InMemoryWorkflowBenchmarkExecutionRepository:
    """Store immutable benchmark execution records in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._executions: dict[
            UUID,
            WorkflowBenchmarkExecutionRecord,
        ] = {}

    def save(
        self,
        execution: WorkflowBenchmarkExecutionRecord,
    ) -> None:
        """Persist one execution without replacing existing evidence.

        Raises:
            ValueError: An execution with the same identifier already exists.
        """

        if execution.id in self._executions:
            raise ValueError(f"Benchmark execution {execution.id} already exists.")

        self._executions[execution.id] = execution

    def get(
        self,
        execution_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return one execution by identifier."""

        return self._executions.get(execution_id)

    def executions(
        self,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return all executions in insertion order."""

        return tuple(self._executions.values())

    def executions_for_benchmark(
        self,
        benchmark_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions of one benchmark in insertion order."""

        return tuple(
            execution
            for execution in self._executions.values()
            if execution.benchmark_id == benchmark_id
        )

    def executions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions that judged one workflow, in insertion order."""

        return tuple(
            execution
            for execution in self._executions.values()
            if any(candidate.workflow.id == workflow_id for candidate in execution.candidates)
        )

    def execution_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return the execution that produced one workflow run."""

        return next(
            (
                execution
                for execution in self._executions.values()
                if execution.candidate_for_run(run_id) is not None
            ),
            None,
        )


def require_workflow_benchmark_execution_repository(
    repository: WorkflowBenchmarkExecutionRepository,
) -> WorkflowBenchmarkExecutionRepository:
    """Return a repository after static protocol validation."""

    return repository
