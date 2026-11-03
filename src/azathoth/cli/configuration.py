"""Configuration for bootstrapping the Azathoth CLI runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import SecretStr

from azathoth.inputs import S3ContentLocation, content_store_location
from azathoth.persistence import (
    DatabaseLocation,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
)
from azathoth.providers import (
    AWS_DEFAULT_REGION_VARIABLE,
    AWS_REGION_VARIABLE,
    BEDROCK_ENABLED_VARIABLE,
    BEDROCK_PRICING_VARIABLE,
    bedrock_enabled,
)

DEFAULT_DATABASE = Path("azathoth.db")

DATABASE_ENVIRONMENT_VARIABLE = "AZATHOTH_DATABASE"

OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE = "OPENROUTER_API_KEY"

BEDROCK_ENVIRONMENT_VARIABLES = (
    BEDROCK_ENABLED_VARIABLE,
    BEDROCK_PRICING_VARIABLE,
    AWS_REGION_VARIABLE,
    AWS_DEFAULT_REGION_VARIABLE,
)
"""The variables Azathoth reads to configure Bedrock (ADR 0103).

AWS's credentials are not among them: boto3 finds those itself.
"""


@dataclass(
    frozen=True,
    slots=True,
)
class CliRuntimeConfiguration:
    """Describe process-local configuration required to bootstrap the CLI.

    The database is an SQLite file's path, or a PostgreSQL database named by
    a `postgresql://` URL (ADR 0102).

    `bedrock_environment` holds the Bedrock variables that were set, when
    `AZATHOTH_BEDROCK` turns Bedrock on, and is empty otherwise (ADR 0103).
    They are read only when the runtime is composed, so a command that
    composes none never imports boto3.

    `content_store` is the S3 location `AZATHOTH_CONTENT_STORE` names, or
    `None` to keep resolved content in the database (ADR 0108).
    """

    database: Path | PostgresLocation = DEFAULT_DATABASE
    openrouter_api_key: SecretStr | None = None
    bedrock_environment: tuple[tuple[str, str], ...] = ()
    content_store: S3ContentLocation | None = None

    @property
    def bedrock_enabled(
        self,
    ) -> bool:
        """Return whether Bedrock is on."""

        return bedrock_enabled(dict(self.bedrock_environment))

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
        """Construct CLI runtime configuration from environment variables.

        Raises:
            ContentStoreError: `AZATHOTH_CONTENT_STORE` is set, but not to an
                `s3://` URL.
        """

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

        bedrock = (
            tuple((name, values[name]) for name in BEDROCK_ENVIRONMENT_VARIABLES if name in values)
            if bedrock_enabled(values)
            else ()
        )

        return cls(
            database=database,
            openrouter_api_key=api_key,
            bedrock_environment=bedrock,
            content_store=content_store_location(values),
        )
