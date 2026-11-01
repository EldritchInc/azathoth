"""Database initialization for the Azathoth CLI (ADR 0095, ADR 0102)."""

import sqlite3
import sys

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.tools import install_standard_tools
from azathoth.persistence import (
    DatabaseSchemaError,
    DatabaseUnavailableError,
    InitializationOutcome,
    PostgresLocation,
    SQLiteLocation,
)
from azathoth.persistence.repositories import SCHEMA_TABLES, postgres_database


def initialize_database() -> int:
    """Create the configured database if needed and install the standard tools.

    The database is the one `AZATHOTH_DATABASE` names, or `azathoth.db` in the
    working directory. It is shown, marked as created or existing, and the
    standard tool library is then installed exactly as by
    `azathoth tool install-standard`, so running `init` again is always safe.

    An SQLite database is shown as an absolute path, and missing parent
    directories are created. A PostgreSQL database is shown by its URL
    without its password, and its schema is created, or brought up to date,
    under a lock, so several processes may initialize it at once.

    Initialization stops at the database and its tools. Authorizing models
    needs provider credentials, so it stays a separate step.
    """

    location = CliRuntimeConfiguration.from_environment().location

    if isinstance(location, PostgresLocation):
        status = _initialize_postgres(location)
    else:
        status = _initialize_sqlite(location)

    if status != 0:
        return status

    return install_standard_tools()


def _initialize_sqlite(
    location: SQLiteLocation,
) -> int:
    """Create an SQLite database file, and report whether it existed."""

    database = location.path.absolute()

    existed = database.exists()

    try:
        database.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        sqlite3.connect(database).close()
    except (OSError, sqlite3.Error) as exc:
        print(
            f"Unable to open database {database}: {exc}",
            file=sys.stderr,
        )

        return 1

    print(f"Database: {database} ({'existing' if existed else 'created'})")

    return 0


def _initialize_postgres(
    location: PostgresLocation,
) -> int:
    """Create or update a PostgreSQL schema, and report whether it existed."""

    try:
        outcome = postgres_database(location).initialize(SCHEMA_TABLES)
    except (DatabaseUnavailableError, DatabaseSchemaError) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1
    except Exception as exc:
        print(
            f"Unable to open database {location.display()}: {exc}",
            file=sys.stderr,
        )

        return 1

    created = outcome is InitializationOutcome.CREATED

    print(f"Database: {location.display()} ({'created' if created else 'existing'})")

    return 0


__all__ = [
    "initialize_database",
]
