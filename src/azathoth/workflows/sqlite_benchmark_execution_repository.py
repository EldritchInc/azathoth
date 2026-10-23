"""SQLite persistence for durable workflow benchmark execution records."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.benchmark_record import (
    WorkflowBenchmarkExecutionRecord,
)


class SQLiteWorkflowBenchmarkExecutionRepository:
    """Persist immutable benchmark execution records in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

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

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
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
                        connection.execute(
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

                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError(f"Benchmark execution {execution.id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        execution_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return one execution by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_benchmark_executions
                WHERE execution_id = ?
                """,
                (str(execution_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def executions(
        self,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return all executions in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_benchmark_executions
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def executions_for_benchmark(
        self,
        benchmark_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions of one benchmark in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_benchmark_executions
                WHERE benchmark_id = ?
                ORDER BY sequence
                """,
                (str(benchmark_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def executions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
        """Return executions that judged one workflow, in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT execution.payload
                FROM workflow_benchmark_executions AS execution
                JOIN workflow_benchmark_execution_cases AS execution_case
                    ON execution_case.execution_id = execution.execution_id
                WHERE execution_case.workflow_id = ?
                GROUP BY execution.execution_id
                ORDER BY execution.sequence
                """,
                (str(workflow_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def execution_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowBenchmarkExecutionRecord | None:
        """Return the execution that produced one workflow run."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
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
            ).fetchone()
        finally:
            connection.close()

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

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted benchmark execution payload was not text.")

        return WorkflowBenchmarkExecutionRecord.model_validate_json(payload)

    def _initialize(self) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_benchmark_executions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL UNIQUE,
                    benchmark_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_benchmark_executions_benchmark_id
                ON workflow_benchmark_executions (
                    benchmark_id,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_benchmark_execution_cases (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
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
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_benchmark_execution_cases_workflow_id
                ON workflow_benchmark_execution_cases (
                    workflow_id,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_benchmark_execution_cases_run_id
                ON workflow_benchmark_execution_cases (
                    run_id,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()
