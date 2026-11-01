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
)
from azathoth.persistence.location import (
    POSTGRES_SCHEMES,
    DatabaseLocation,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
    redact_url,
)
from azathoth.persistence.opening import open_database
from azathoth.persistence.postgres import PostgresDatabase
from azathoth.persistence.sqlite import SQLiteDatabase

__all__ = [
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
    "Row",
    "SQLiteDatabase",
    "SQLiteLocation",
    "Session",
    "Table",
    "open_database",
    "parse_database_location",
    "redact_url",
]
