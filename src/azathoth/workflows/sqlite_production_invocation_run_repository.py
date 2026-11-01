"""SQLite persistence for production invocation run associations."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_production_invocation_run_repository import (
    SqlProductionInvocationRunRepository,
)


class SQLiteProductionInvocationRunRepository(SqlProductionInvocationRunRepository):
    """Persist production invocation run associations in SQLite."""

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        """Initialize SQLite invocation run persistence."""

        super().__init__(SQLiteDatabase(path))
