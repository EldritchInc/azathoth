"""SQLite persistence for reusable goals."""

from pathlib import Path

from azathoth.goals.sql_repository import SqlGoalRepository
from azathoth.persistence import SQLiteDatabase


class SQLiteGoalRepository(SqlGoalRepository):
    """Persist immutable goals in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
