"""Where Azathoth keeps its durable state (ADR 0102)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    "POSTGRES_SCHEMES",
    "DatabaseLocation",
    "PostgresLocation",
    "SQLiteLocation",
    "is_postgres_url",
    "parse_database_location",
    "redact_url",
]
