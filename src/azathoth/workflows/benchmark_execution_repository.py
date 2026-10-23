"""Persistence contracts for durable workflow benchmark execution records."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.benchmark_record import (
    WorkflowBenchmarkExecutionRecord,
)


class WorkflowBenchmarkExecutionRepository(Protocol):
    """Persist and retrieve completed benchmark execution records."""

    def save(
        self,
        execution: WorkflowBenchmarkExecutionRecord,
    ) -> None:
        """Persist one completed benchmark execution.

        Raises:
            ValueError: An execution with the same identifier already exists.
        """

        ...

    def get(
        self,
        execution_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return one execution by identifier."""

        ...

    def executions(
        self,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return all executions in insertion order."""

        ...

    def executions_for_benchmark(
        self,
        benchmark_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions of one benchmark in insertion order."""

        ...

    def executions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions that judged one workflow, in insertion order."""

        ...

    def execution_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return the execution that produced one workflow run."""

        ...
