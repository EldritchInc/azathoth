"""SQLite persistence for durable workflow experiment records."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_experiment_repository import SqlWorkflowExperimentRepository


class SQLiteWorkflowExperimentRepository(SqlWorkflowExperimentRepository):
    """Persist immutable workflow experiment records in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
