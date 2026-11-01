"""SQLite persistence for the semantic judge rotation."""

from pathlib import Path

from azathoth.evaluation.sql_judge_repository import SqlJudgeRotationRepository
from azathoth.persistence import SQLiteDatabase


class SQLiteJudgeRotationRepository(SqlJudgeRotationRepository):
    """Persist the semantic judge rotation in SQLite, in insertion order."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
