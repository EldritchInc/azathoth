"""Opening an Azathoth instance through the service API (ADR 0120)."""

from pathlib import Path
from types import TracebackType

import azathoth
from azathoth.api.errors import (
    InstanceClosedError,
    InstanceNotFoundError,
    InstanceSchemaError,
    InstanceUnavailableError,
)
from azathoth.api.models import API_STABILITY, InstanceDescription
from azathoth.persistence import (
    SCHEMA_VERSION,
    DatabaseLocation,
    DatabaseSchemaError,
    DatabaseUnavailableError,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
)
from azathoth.persistence.repositories import (
    SCHEMA_TABLES,
    Repositories,
    open_repositories,
)


class Azathoth:
    """One open Azathoth instance: the database every call reads and writes.

    Open one with `azathoth.api.open`, and close it when done, best as a
    context manager. Calls run synchronously on the caller's thread. Once
    closed, every call raises `InstanceClosedError`.
    """

    def __init__(
        self,
        repositories: Repositories,
    ) -> None:
        """Serve the API over one database's repositories; `open` is the way to make one."""

        self._repositories = repositories
        self._closed = False

    def __enter__(
        self,
    ) -> "Azathoth":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def closed(
        self,
    ) -> bool:
        """Return whether the instance was closed."""

        return self._closed

    def describe(
        self,
    ) -> InstanceDescription:
        """Return what this instance is: its database, and the Azathoth serving it.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        location = self._open_repositories().location

        return InstanceDescription(
            database=location.display(),
            backend="postgres" if isinstance(location, PostgresLocation) else "sqlite",
            azathoth_version=azathoth.__version__,
            schema_version=SCHEMA_VERSION,
            api_stability=API_STABILITY,
        )

    def close(
        self,
    ) -> None:
        """Release the database's connection, if it holds one; closing again does nothing."""

        if self._closed:
            return

        self._closed = True
        self._repositories.database.close()

    def _open_repositories(
        self,
    ) -> Repositories:
        """Return the repositories, unless the instance was closed.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        if self._closed:
            raise InstanceClosedError()

        return self._repositories


def open(
    database: DatabaseLocation | str | Path,
) -> Azathoth:
    """Open the Azathoth instance one database holds.

    The database is named as `AZATHOTH_DATABASE` names it: an SQLite file's
    path, or a `postgresql://` URL. Opening never creates or changes a
    database; `azathoth init` does.

    Raises:
        InstanceNotFoundError: The SQLite file does not exist.
        InstanceUnavailableError: It is a PostgreSQL database, and the
            `postgres` extra is not installed.
        InstanceSchemaError: The PostgreSQL database does not hold this
            Azathoth's schema.
    """

    location = (
        database
        if isinstance(database, SQLiteLocation | PostgresLocation)
        else parse_database_location(database)
    )

    if isinstance(location, SQLiteLocation) and not location.path.is_file():
        raise InstanceNotFoundError(
            f"Database {location.display()} does not exist; run azathoth init."
        )

    try:
        repositories = open_repositories(location)
    except DatabaseUnavailableError as exc:
        raise InstanceUnavailableError(str(exc)) from exc

    if isinstance(location, PostgresLocation):
        try:
            repositories.database.prepare(SCHEMA_TABLES)
        except DatabaseSchemaError as exc:
            raise InstanceSchemaError(str(exc)) from exc

    return Azathoth(repositories)


__all__ = [
    "Azathoth",
    "open",
]
