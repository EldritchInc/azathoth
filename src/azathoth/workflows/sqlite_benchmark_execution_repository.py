"""SQLite persistence for durable workflow benchmark execution records."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_benchmark_execution_repository import (
    SqlWorkflowBenchmarkExecutionRepository,
)


class SQLiteWorkflowBenchmarkExecutionRepository(SqlWorkflowBenchmarkExecutionRepository):
    """Persist immutable benchmark execution records in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
