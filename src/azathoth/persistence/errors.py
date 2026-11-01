"""Errors of Azathoth's persistence layer (ADR 0102)."""

from typing import Final

from azathoth.persistence.location import DatabaseLocation

MISSING_DRIVER_MESSAGE: Final = (
    "AZATHOTH_DATABASE names a PostgreSQL database, but psycopg is not installed; "
    "install azathoth-ai[postgres]."
)


class PersistenceError(Exception):
    """Base class of the errors a database raises in Azathoth's own terms."""


class IntegrityError(PersistenceError):
    """A statement would have broken a constraint, such as a unique key.

    Both databases raise it, so a repository maps a duplicate once, whichever
    database it runs on.
    """


class DatabaseUnavailableError(PersistenceError):
    """The database cannot be used here: PostgreSQL without the `postgres` extra."""

    def __init__(
        self,
    ) -> None:
        super().__init__(MISSING_DRIVER_MESSAGE)


class DatabaseSchemaError(PersistenceError):
    """The database's schema is not the one this Azathoth uses."""


class DatabaseNotInitializedError(DatabaseSchemaError):
    """The PostgreSQL database holds no Azathoth schema yet."""

    def __init__(
        self,
        location: DatabaseLocation,
    ) -> None:
        super().__init__(f"Database {location.display()} is not initialized; run azathoth init.")


class DatabaseSchemaOutdatedError(DatabaseSchemaError):
    """The PostgreSQL database's schema is older than this Azathoth's."""

    def __init__(
        self,
        location: DatabaseLocation,
        *,
        found: int,
        expected: int,
    ) -> None:
        super().__init__(
            f"Database {location.display()} has schema version {found}, but this Azathoth "
            f"uses version {expected}; run azathoth init."
        )


class DatabaseSchemaTooNewError(DatabaseSchemaError):
    """The PostgreSQL database's schema is newer than this Azathoth understands."""

    def __init__(
        self,
        location: DatabaseLocation,
        *,
        found: int,
        expected: int,
    ) -> None:
        super().__init__(
            f"Database {location.display()} has schema version {found}, newer than the "
            f"version {expected} this Azathoth uses; upgrade Azathoth."
        )


__all__ = [
    "MISSING_DRIVER_MESSAGE",
    "DatabaseNotInitializedError",
    "DatabaseSchemaError",
    "DatabaseSchemaOutdatedError",
    "DatabaseSchemaTooNewError",
    "DatabaseUnavailableError",
    "IntegrityError",
    "PersistenceError",
]
