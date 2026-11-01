"""Tests for naming the database (ADR 0102)."""

from pathlib import Path

import pytest

from azathoth.persistence import (
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
    redact_url,
)

URL = "postgresql://azathoth:s3cr%40t@db.example.internal:5432/azathoth"


@pytest.mark.parametrize(
    "value",
    [
        URL,
        "postgres://azathoth@db.example.internal/azathoth",
        "POSTGRESQL://db.example.internal/azathoth",
        "postgresql:///azathoth",
    ],
)
def test_a_postgresql_url_names_a_postgresql_database(
    value: str,
) -> None:
    assert parse_database_location(value) == PostgresLocation(url=value)


@pytest.mark.parametrize(
    "value",
    [
        "azathoth.db",
        "/var/lib/azathoth/azathoth.db",
        "C:\\Users\\you\\azathoth.db",
        "C:/Users/you/azathoth.db",
        "postgresql.db",
        "mysql://db.example.internal/azathoth",
    ],
)
def test_anything_else_is_an_sqlite_path(
    value: str,
) -> None:
    assert parse_database_location(value) == SQLiteLocation(path=Path(value))


def test_a_path_is_always_an_sqlite_path() -> None:
    path = Path("postgresql://not/a/url")

    assert parse_database_location(path) == SQLiteLocation(path=path)


def test_an_sqlite_database_is_named_by_its_path() -> None:
    assert SQLiteLocation(path=Path("/data/azathoth.db")).display() == str(
        Path("/data/azathoth.db")
    )


# Never showing a secret


def test_the_password_is_removed() -> None:
    assert redact_url(URL) == "postgresql://azathoth@db.example.internal:5432/azathoth"


def test_secret_parameters_are_removed_and_the_rest_kept() -> None:
    url = "postgresql://db.example.internal/azathoth?sslmode=require&password=hunter2&passfile=/p"

    assert redact_url(url) == "postgresql://db.example.internal/azathoth?sslmode=require"


def test_a_password_without_a_user_is_removed() -> None:
    assert redact_url("postgresql://:hunter2@db/azathoth") == "postgresql://db/azathoth"


def test_a_url_without_secrets_is_unchanged() -> None:
    url = "postgresql://azathoth@db.example.internal:5432/azathoth?sslmode=verify-full"

    assert redact_url(url) == url


def test_a_location_never_shows_its_password() -> None:
    location = PostgresLocation(url=URL)

    assert location.display() == "postgresql://azathoth@db.example.internal:5432/azathoth"
    assert "s3cr" not in repr(location)
    assert "s3cr" not in str(location)
