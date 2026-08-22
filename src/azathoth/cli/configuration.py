"""Configuration for bootstrapping the Azathoth CLI runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import SecretStr

DEFAULT_DATABASE = Path("azathoth.db")

DATABASE_ENVIRONMENT_VARIABLE = "AZATHOTH_DATABASE"

OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE = "OPENROUTER_API_KEY"


@dataclass(
    frozen=True,
    slots=True,
)
class CliRuntimeConfiguration:
    """Describe process-local configuration required to bootstrap the CLI."""

    database: Path = DEFAULT_DATABASE
    openrouter_api_key: SecretStr | None = None

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "CliRuntimeConfiguration":
        """Construct CLI runtime configuration from environment variables."""

        values = environment if environment is not None else os.environ

        database_value = values.get(DATABASE_ENVIRONMENT_VARIABLE)

        api_key_value = values.get(OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE)

        database = Path(database_value) if database_value else DEFAULT_DATABASE

        api_key = SecretStr(api_key_value) if api_key_value else None

        return cls(
            database=database,
            openrouter_api_key=api_key,
        )
