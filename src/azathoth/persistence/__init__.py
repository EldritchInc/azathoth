"""Azathoth's durable state, in SQLite or PostgreSQL (ADR 0102).

Each repository is written once, against `Database`, and runs on either
database. Importing this package imports nothing of psycopg; opening a
PostgreSQL database does.
"""

from azathoth.persistence.database import (
    SCHEMA_TABLE,
    SCHEMA_VERSION,
    Database,
    InitializationOutcome,
    Parameter,
    Row,
    Session,
    Table,
    run_backfills,
)
from azathoth.persistence.dialect import Dialect
from azathoth.persistence.errors import (
    MISSING_DRIVER_MESSAGE,
    DatabaseNotInitializedError,
    DatabaseSchemaError,
    DatabaseSchemaOutdatedError,
    DatabaseSchemaTooNewError,
    DatabaseUnavailableError,
    IntegrityError,
    PersistenceError,
    ReadOnlyTransactionError,
)
from azathoth.persistence.location import (
    DATABASE_VARIABLE,
    DEFAULT_DATABASE,
    POSTGRES_SCHEMES,
    DatabaseLocation,
    PostgresLocation,
    SQLiteLocation,
    database_location,
    parse_database_location,
    redact_url,
)
from azathoth.persistence.opening import open_database
from azathoth.persistence.postgres import PostgresDatabase
from azathoth.persistence.sqlite import SQLiteDatabase
from azathoth.persistence.values import require_integer, require_text

__all__ = [
    "DATABASE_VARIABLE",
    "DEFAULT_DATABASE",
    "MISSING_DRIVER_MESSAGE",
    "POSTGRES_SCHEMES",
    "SCHEMA_TABLE",
    "SCHEMA_VERSION",
    "Database",
    "DatabaseLocation",
    "DatabaseNotInitializedError",
    "DatabaseSchemaError",
    "DatabaseSchemaOutdatedError",
    "DatabaseSchemaTooNewError",
    "DatabaseUnavailableError",
    "Dialect",
    "InitializationOutcome",
    "IntegrityError",
    "Parameter",
    "PersistenceError",
    "PostgresDatabase",
    "PostgresLocation",
    "ReadOnlyTransactionError",
    "Row",
    "SQLiteDatabase",
    "SQLiteLocation",
    "Session",
    "Table",
    "database_location",
    "open_database",
    "parse_database_location",
    "redact_url",
    "require_integer",
    "require_text",
    "run_backfills",
]
