"""Where Azathoth keeps its durable state (ADR 0102)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DATABASE_VARIABLE: Final = "AZATHOTH_DATABASE"
"""The environment variable that names the database."""

DEFAULT_DATABASE: Final = Path("azathoth.db")
"""The database when `AZATHOTH_DATABASE` names none: an SQLite file in the working directory."""

POSTGRES_SCHEMES: Final = ("postgresql", "postgres")
"""The URL schemes that name a PostgreSQL database."""

_SECRET_PARAMETERS: Final = frozenset({"password", "passfile", "sslpassword"})


@dataclass(frozen=True)
class SQLiteLocation:
    """An SQLite database file."""

    path: Path

    def display(
        self,
    ) -> str:
        """Return how the database is named in messages: its path."""

        return str(self.path)


@dataclass(frozen=True)
class PostgresLocation:
    """A PostgreSQL database, named by a libpq connection URL.

    The URL may carry credentials, so it is never shown as it is: `display`
    names the database with its password and other secrets removed.
    """

    url: str

    def __repr__(
        self,
    ) -> str:
        return f"PostgresLocation(url={self.display()!r})"

    def display(
        self,
    ) -> str:
        """Return how the database is named in messages, with no secret in it."""

        return redact_url(self.url)


DatabaseLocation = SQLiteLocation | PostgresLocation
"""Where one database is: an SQLite file, or a PostgreSQL server."""


def is_postgres_url(
    value: str,
) -> bool:
    """Return whether a value is a PostgreSQL URL, rather than a path."""

    scheme, separator, _ = value.partition("://")

    return bool(separator) and scheme.lower() in POSTGRES_SCHEMES


def parse_database_location(
    value: str | Path,
) -> DatabaseLocation:
    """Return the database one `AZATHOTH_DATABASE` value names.

    A `postgresql://` or `postgres://` URL names a PostgreSQL database;
    anything else, including a Windows path with a drive letter, is the path
    of an SQLite file.
    """

    if isinstance(value, str) and is_postgres_url(value):
        return PostgresLocation(url=value)

    return SQLiteLocation(path=Path(value))


def database_location(
    environment: Mapping[str, str] | None = None,
) -> DatabaseLocation:
    """Return the database `AZATHOTH_DATABASE` names, or `azathoth.db` when it names none.

    It is how the command line, and so `azathoth remote serve`, finds its
    database, and how a remote's plugin finds the same one (ADR 0134). An
    empty value names none. `environment` defaults to the process's own.
    """

    values = os.environ if environment is None else environment
    named = values.get(DATABASE_VARIABLE)

    return parse_database_location(named) if named else SQLiteLocation(path=DEFAULT_DATABASE)


def redact_url(
    url: str,
) -> str:
    """Return a PostgreSQL URL with its password, and any secret parameter, removed."""

    parts = urlsplit(url)
    userinfo, at, hostinfo = parts.netloc.rpartition("@")

    netloc = parts.netloc

    if at:
        user = userinfo.partition(":")[0]
        netloc = f"{user}@{hostinfo}" if user else hostinfo

    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _SECRET_PARAMETERS
        ]
    )

    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


__all__ = [
    "DATABASE_VARIABLE",
    "DEFAULT_DATABASE",
    "POSTGRES_SCHEMES",
    "DatabaseLocation",
    "PostgresLocation",
    "SQLiteLocation",
    "database_location",
    "is_postgres_url",
    "parse_database_location",
    "redact_url",
]
