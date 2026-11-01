"""Opening the database a location names (ADR 0102)."""

from pathlib import Path

from azathoth.persistence.database import Database
from azathoth.persistence.location import (
    DatabaseLocation,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
)
from azathoth.persistence.postgres import PostgresDatabase
from azathoth.persistence.sqlite import SQLiteDatabase


def open_database(
    location: DatabaseLocation | str | Path,
) -> Database:
    """Return the database one location, or one `AZATHOTH_DATABASE` value, names.

    Raises:
        DatabaseUnavailableError: It is a PostgreSQL database, and the
            `postgres` extra is not installed.
    """

    resolved = (
        location
        if isinstance(location, SQLiteLocation | PostgresLocation)
        else parse_database_location(location)
    )

    if isinstance(resolved, PostgresLocation):
        return PostgresDatabase(resolved)

    return SQLiteDatabase(resolved.path)


__all__ = [
    "open_database",
]
