"""SQLite persistence for active workflow production state."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_production_repository import SqlWorkflowProductionStateRepository


class SQLiteWorkflowProductionStateRepository(SqlWorkflowProductionStateRepository):
    """Persist active workflow production state in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
