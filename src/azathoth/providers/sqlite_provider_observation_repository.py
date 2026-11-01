"""SQLite persistence for provider model observations."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.providers.sql_provider_observation_repository import (
    SqlProviderModelObservationRepository,
)


class SQLiteProviderModelObservationRepository(SqlProviderModelObservationRepository):
    """Persist immutable provider model observations in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
