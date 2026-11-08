"""Fixtures that run each contract of `azathoth.api` on SQLite, and on PostgreSQL when named.

Every test that takes `instance` runs once per backend. The PostgreSQL run
needs a server named by `AZATHOTH_TEST_POSTGRES_URL` (`make postgres-test`
starts one); without it, that half is skipped. Each PostgreSQL test gets a
schema of its own, initialized as `azathoth init` would, and dropped
afterwards.
"""

import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from azathoth import api
from azathoth.persistence import PostgresDatabase
from azathoth.persistence.repositories import SCHEMA_TABLES
from tests.persistence.conftest import (
    POSTGRES_URL_VARIABLE,
    postgres_server_url,
    with_search_path,
)

BACKENDS = ("sqlite", "postgres")


@pytest.fixture
def empty_postgres_url() -> Iterator[str]:
    """Return the URL of a fresh PostgreSQL schema holding nothing, or skip without a server."""

    server = postgres_server_url()

    if server is None:
        pytest.skip(f"PostgreSQL contract tests require {POSTGRES_URL_VARIABLE}.")

    import psycopg

    schema = f"azathoth_api_{uuid.uuid4().hex[:16]}"

    with psycopg.connect(server, autocommit=True) as connection:
        connection.execute(f"CREATE SCHEMA {schema}")

    try:
        yield with_search_path(server, schema)
    finally:
        with psycopg.connect(server, autocommit=True) as connection:
            connection.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture(params=BACKENDS)
def location(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> str:
    """Return an initialized database of each kind in turn, as `AZATHOTH_DATABASE` names it."""

    if request.param == "sqlite":
        path = tmp_path / "azathoth.db"
        sqlite3.connect(path).close()

        return str(path)

    url: str = request.getfixturevalue("empty_postgres_url")
    database = PostgresDatabase(url)

    try:
        database.initialize(SCHEMA_TABLES)
    finally:
        database.close()

    return url


@pytest.fixture
def instance(
    location: str,
) -> Iterator[api.Azathoth]:
    """Return an open instance over each kind of database in turn, closed afterwards."""

    with api.open(location) as opened:
        yield opened
