"""SQLite persistence for immutable workflow production revisions."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_production_revision_repository import (
    SqlWorkflowProductionRevisionRepository,
)


class SQLiteWorkflowProductionRevisionRepository(SqlWorkflowProductionRevisionRepository):
    """Persist immutable workflow production revisions in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
