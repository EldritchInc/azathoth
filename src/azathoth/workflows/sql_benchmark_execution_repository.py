"""Durable workflow benchmark execution records, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table
from azathoth.workflows.benchmark_record import (
    WorkflowBenchmarkExecutionRecord,
)

WORKFLOW_BENCHMARK_EXECUTION_TABLES = (
    Table(
        name="workflow_benchmark_executions",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_benchmark_executions (
                sequence {sequence},
                execution_id TEXT NOT NULL UNIQUE,
                benchmark_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_benchmark_executions_benchmark_id
            ON workflow_benchmark_executions (
                benchmark_id,
                sequence
            )
            """,
        ),
    ),
    Table(
        name="workflow_benchmark_execution_cases",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_benchmark_execution_cases (
                sequence {sequence},
                execution_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                evaluation_id TEXT NOT NULL,
                UNIQUE (
                    execution_id,
                    run_id
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_benchmark_execution_cases_workflow_id
            ON workflow_benchmark_execution_cases (
                workflow_id,
                sequence
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_benchmark_execution_cases_run_id
            ON workflow_benchmark_execution_cases (
                run_id,
                sequence
            )
            """,
        ),
    ),
)
"""The tables benchmark executions, and the index of their cases, are kept in."""


class SqlWorkflowBenchmarkExecutionRepository:
    """Persist immutable benchmark execution records in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(WORKFLOW_BENCHMARK_EXECUTION_TABLES)

    def save(
        self,
        execution: WorkflowBenchmarkExecutionRecord,
    ) -> None:
        """Persist one execution without replacing existing evidence.

        Every case of every candidate is indexed by candidate, workflow, case,
        run, and evaluation, so executions can be found by the workflows they
        judged and the runs they produced. The record and its index are
        written in one transaction.

        Raises:
            ValueError: An execution with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
                    """
                    INSERT INTO workflow_benchmark_executions (
                        execution_id,
                        benchmark_id,
                        payload
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(execution.id),
                        str(execution.benchmark_id),
                        execution.model_dump_json(),
                    ),
                )

                for candidate in execution.candidates:
                    for case in candidate.cases:
                        session.execute(
                            """
                            INSERT INTO workflow_benchmark_execution_cases (
                                execution_id,
                                candidate_id,
                                workflow_id,
                                case_id,
                                run_id,
                                evaluation_id
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                str(execution.id),
                                str(candidate.id),
                                str(candidate.workflow.id),
                                str(case.case_id),
                                str(case.run_id),
                                str(case.evaluation_id),
                            ),
                        )
        except IntegrityError as exc:
            raise ValueError(f"Benchmark execution {execution.id} already exists.") from exc

    def get(
        self,
        execution_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return one execution by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_benchmark_executions
                WHERE execution_id = ?
                """,
                (str(execution_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def executions(
        self,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return all executions in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_benchmark_executions
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def executions_for_benchmark(
        self,
        benchmark_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions of one benchmark in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_benchmark_executions
                WHERE benchmark_id = ?
                ORDER BY sequence
                """,
                (str(benchmark_id),),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def executions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions that judged one workflow, in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT execution.payload
                FROM workflow_benchmark_executions AS execution
                WHERE EXISTS (
                    SELECT 1
                    FROM workflow_benchmark_execution_cases AS execution_case
                    WHERE execution_case.execution_id = execution.execution_id
                        AND execution_case.workflow_id = ?
                )
                ORDER BY execution.sequence
                """,
                (str(workflow_id),),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def execution_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return the execution that produced one workflow run."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT execution.payload
                FROM workflow_benchmark_executions AS execution
                JOIN workflow_benchmark_execution_cases AS execution_case
                    ON execution_case.execution_id = execution.execution_id
                WHERE execution_case.run_id = ?
                ORDER BY execution.sequence
                LIMIT 1
                """,
                (str(run_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowBenchmarkExecutionRecord:
        """Reconstruct one persisted benchmark execution.

        Raises:
            TypeError: The persisted payload is not text.
        """

        if not isinstance(payload, str):
            raise TypeError("Persisted benchmark execution payload was not text.")

        return WorkflowBenchmarkExecutionRecord.model_validate_json(payload)


__all__ = [
    "WORKFLOW_BENCHMARK_EXECUTION_TABLES",
    "SqlWorkflowBenchmarkExecutionRepository",
]
