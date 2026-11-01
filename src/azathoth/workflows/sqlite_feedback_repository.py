"""SQLite persistence for immutable workflow run feedback."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.workflows.sql_feedback_repository import SqlWorkflowRunFeedbackRepository


class SQLiteWorkflowRunFeedbackRepository(SqlWorkflowRunFeedbackRepository):
    """Persist workflow run feedback in a SQLite database."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
