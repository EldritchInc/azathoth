"""The repositories the CLI keeps its durable state in (ADR 0102)."""

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.persistence.repositories import Repositories, open_repositories


def repositories(
    configuration: CliRuntimeConfiguration,
) -> Repositories:
    """Return the repositories of the configured database.

    Each is opened the first time it is used. Every PostgreSQL repository of
    the process shares one connection.

    Raises:
        DatabaseUnavailableError: The database is PostgreSQL, and the
            `postgres` extra is not installed.
    """

    return open_repositories(configuration.location)


__all__ = [
    "repositories",
]
