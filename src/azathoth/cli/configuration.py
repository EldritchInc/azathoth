"""Configuration for bootstrapping the Azathoth CLI runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import SecretStr

from azathoth.persistence import (
    DatabaseLocation,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
)

DEFAULT_DATABASE = Path("azathoth.db")

DATABASE_ENVIRONMENT_VARIABLE = "AZATHOTH_DATABASE"

OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE = "OPENROUTER_API_KEY"


@dataclass(
    frozen=True,
    slots=True,
)
class CliRuntimeConfiguration:
    """Describe process-local configuration required to bootstrap the CLI.

    The database is an SQLite file's path, or a PostgreSQL database named by
    a `postgresql://` URL (ADR 0102).
    """

    database: Path | PostgresLocation = DEFAULT_DATABASE
    openrouter_api_key: SecretStr | None = None

    @property
    def location(
        self,
    ) -> DatabaseLocation:
        """Return where the configured database is."""

        if isinstance(self.database, PostgresLocation):
            return self.database

        return SQLiteLocation(path=self.database)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "CliRuntimeConfiguration":
        """Construct CLI runtime configuration from environment variables."""

        values = environment if environment is not None else os.environ

        database_value = values.get(DATABASE_ENVIRONMENT_VARIABLE)

        api_key_value = values.get(OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE)

        location = parse_database_location(database_value) if database_value else None

        database: Path | PostgresLocation = (
            location
            if isinstance(location, PostgresLocation)
            else location.path
            if location is not None
            else DEFAULT_DATABASE
        )

        api_key = SecretStr(api_key_value) if api_key_value else None

        return cls(
            database=database,
            openrouter_api_key=api_key,
        )
