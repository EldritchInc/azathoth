"""SQLite persistence for immutable workflow run evaluations."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_run_evaluation_repository import (
    SqlWorkflowRunEvaluationRepository,
)


class SQLiteWorkflowRunEvaluationRepository(SqlWorkflowRunEvaluationRepository):
    """Persist workflow run evaluations in a SQLite database."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
