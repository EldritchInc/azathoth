"""Initializing a database through the service API (ADR 0120).

`initialize` does what `azathoth init` does: it creates an SQLite file, or
creates or upgrades a PostgreSQL schema, and installs the standard tool
library. Running it again is always safe.
"""

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal

from azathoth.api.errors import InstanceSchemaError, InstanceUnavailableError
from azathoth.api.models import Initialization
from azathoth.api.standard_tools import install_standard_tools
from azathoth.persistence import (
    DatabaseLocation,
    DatabaseSchemaError,
    DatabaseUnavailableError,
    InitializationOutcome,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
)
from azathoth.persistence.repositories import (
    SCHEMA_TABLES,
    open_repositories,
)

OUTCOMES: Final[Mapping[InitializationOutcome, Literal["created", "upgraded", "current"]]] = {
    InitializationOutcome.CREATED: "created",
    InitializationOutcome.UPGRADED: "upgraded",
    InitializationOutcome.CURRENT: "current",
}
"""What each outcome of initializing a database is called."""


def initialize(
    database: DatabaseLocation | str | Path,
) -> Initialization:
    """Create the database one location names, if needed, and install the standard tools.

    An SQLite file's missing parent directories are created. A PostgreSQL
    schema is created, or brought up to date, under a lock, so several
    processes may initialize it at once. Each standard tool whose latest
    revision has other content gets the standard document as its next
    revision; one that is already current is left alone.

    Raises:
        InstanceUnavailableError: The database cannot be opened or made, or
            it is PostgreSQL without the `postgres` extra.
        InstanceSchemaError: The PostgreSQL schema is newer than this
            Azathoth's.
        ConflictError: A standard tool's artifact belongs to another tool or
            version in this database; tools before it were installed.
    """

    location = (
        database
        if isinstance(database, SQLiteLocation | PostgresLocation)
        else parse_database_location(database)
    )

    if isinstance(location, PostgresLocation):
        try:
            repositories = open_repositories(location)
            outcome = repositories.database.initialize(SCHEMA_TABLES)
        except DatabaseUnavailableError as exc:
            raise InstanceUnavailableError(str(exc)) from exc
        except DatabaseSchemaError as exc:
            raise InstanceSchemaError(str(exc)) from exc
        except Exception as exc:
            raise InstanceUnavailableError(
                f"Unable to open database {location.display()}: {exc}"
            ) from exc

        shown = location.display()
    else:
        path = location.path.absolute()
        existed = path.exists()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            sqlite3.connect(path).close()
        except (OSError, sqlite3.Error) as exc:
            raise InstanceUnavailableError(f"Unable to open database {path}: {exc}") from exc

        repositories = open_repositories(SQLiteLocation(path=path))
        outcome = InitializationOutcome.CURRENT if existed else InitializationOutcome.CREATED
        shown = str(path)

    try:
        tools = install_standard_tools(repositories.tools)
    finally:
        repositories.database.close()

    return Initialization(
        database=shown,
        outcome=OUTCOMES[outcome],
        tools=tools,
    )


__all__ = [
    "OUTCOMES",
    "initialize",
]
