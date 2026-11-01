"""SQLite persistence for configured language model metadata."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.providers.sql_repository import SqlModelRepository


class SQLiteModelRepository(SqlModelRepository):
    """Persist immutable model metadata in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
