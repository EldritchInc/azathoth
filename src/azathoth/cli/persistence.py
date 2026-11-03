"""The repositories the CLI keeps its durable state in (ADR 0102)."""

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.inputs import ContentStore, S3ContentLocation, S3ContentStore
from azathoth.persistence.repositories import Repositories, open_repositories


def open_content_store(
    location: S3ContentLocation,
) -> ContentStore:
    """Open the S3 content store `AZATHOTH_CONTENT_STORE` names (ADR 0108).

    Raises:
        ContentStoreError: boto3 is not installed.
    """

    return S3ContentStore(location)


def repositories(
    configuration: CliRuntimeConfiguration,
) -> Repositories:
    """Return the repositories of the configured database.

    Each is opened the first time it is used. Every PostgreSQL repository of
    the process shares one connection. Resolved content is kept in the S3
    store the configuration names, when it names one, and otherwise in the
    database.

    Raises:
        DatabaseUnavailableError: The database is PostgreSQL, and the
            `postgres` extra is not installed.
    """

    location = configuration.content_store

    return open_repositories(
        configuration.location,
        content=(lambda: open_content_store(location)) if location is not None else None,
    )


__all__ = [
    "open_content_store",
    "repositories",
]
