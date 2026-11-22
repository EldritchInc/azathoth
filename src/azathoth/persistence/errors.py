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


class ReadOnlyTransactionError(PersistenceError):
    """A statement in a read-only transaction tried to write.

    Both databases raise it, so a repository that reads in a read-only
    transaction learns of a stray write the same way on either.
    """


class NestedTransactionError(PersistenceError):
    """A transaction was begun inside another one, on the same thread.

    Each transaction holds a connection of its own, so the inner one would
    not see the outer one's writes, and could wait forever on its locks.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            "A transaction was begun inside another on the same thread; "
            "finish the first before beginning the next."
        )


class DatabaseBusyError(PersistenceError):
    """Every pooled connection stayed in use for as long as a transaction waits for one."""

    def __init__(
        self,
        location: DatabaseLocation,
        *,
        pool_size: int,
        waited_seconds: float,
    ) -> None:
        super().__init__(
            f"Database {location.display()} had none of its {pool_size} connections free "
            f"within {waited_seconds:g} seconds."
        )


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
    "DatabaseBusyError",
    "DatabaseNotInitializedError",
    "DatabaseSchemaError",
    "DatabaseSchemaOutdatedError",
    "DatabaseSchemaTooNewError",
    "DatabaseUnavailableError",
    "IntegrityError",
    "NestedTransactionError",
    "PersistenceError",
    "ReadOnlyTransactionError",
]
