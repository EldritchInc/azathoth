"""SQLite persistence for durable workflow run evidence."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_run_repository import SqlWorkflowRunRepository


class SQLiteWorkflowRunRepository(SqlWorkflowRunRepository):
    """Persist immutable workflow run evidence in a SQLite database."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
