"""Fixtures that run each persistence test on SQLite, and on PostgreSQL when one is named.

PostgreSQL tests run only when `AZATHOTH_TEST_POSTGRES_URL` names a server
(`make postgres-test` starts one). Each test then gets a schema of its own,
dropped afterwards, so tests never see each other's tables.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest

from azathoth.persistence import Database, PostgresDatabase, SQLiteDatabase

POSTGRES_URL_VARIABLE = "AZATHOTH_TEST_POSTGRES_URL"

BACKENDS = ("sqlite", "postgres")


def postgres_server_url() -> str | None:
    """Return the PostgreSQL server the tests may use, if one is named."""

    return os.environ.get(POSTGRES_URL_VARIABLE) or None


def with_search_path(
    url: str,
    schema: str,
) -> str:
    """Return a URL whose connections use one schema, and only that one."""

    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "options"
    ]
    query.append(("options", f"-csearch_path={schema}"))

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@pytest.fixture
def postgres_url() -> Iterator[str]:
    """Return the URL of a fresh, empty PostgreSQL schema, or skip without a server."""

    server = postgres_server_url()

    if server is None:
        pytest.skip(f"PostgreSQL tests require {POSTGRES_URL_VARIABLE}.")

    import psycopg

    schema = f"azathoth_test_{uuid.uuid4().hex[:16]}"

    with psycopg.connect(server, autocommit=True) as connection:
        connection.execute(f"CREATE SCHEMA {schema}")

    try:
        yield with_search_path(server, schema)
    finally:
        with psycopg.connect(server, autocommit=True) as connection:
            connection.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture
def postgres_database(
    postgres_url: str,
) -> Iterator[PostgresDatabase]:
    """Return a PostgreSQL database over a fresh schema, closed afterwards."""

    database = PostgresDatabase(postgres_url)

    try:
        yield database
    finally:
        database.close()


@pytest.fixture(params=BACKENDS)
def database(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[Database]:
    """Return a fresh database of each kind in turn."""

    if request.param == "sqlite":
        yield SQLiteDatabase(tmp_path / "azathoth.db")
        return

    yield request.getfixturevalue("postgres_database")
