"""Tests of the lock that keeps one remote server on an SQLite file (ADR 0135)."""

from pathlib import Path

import pytest

from azathoth.persistence import PostgresLocation, SQLiteLocation
from azathoth.remote.serving import (
    SERVE_LOCK_SUFFIX,
    SQLITE_SERVES_ONE_MESSAGE,
    RemoteAlreadyServedError,
    serve_lock_path,
    serving_lock,
)

URL = "postgresql://azathoth@db.example.internal:5432/azathoth"


def test_the_lock_file_sits_beside_the_database() -> None:
    assert SERVE_LOCK_SUFFIX == ".serve-lock"
    assert serve_lock_path(Path("/srv/azathoth/azathoth.db")) == Path(
        "/srv/azathoth/azathoth.db.serve-lock"
    )


def test_a_second_server_on_one_sqlite_file_is_refused_saying_what_to_use(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"
    location = SQLiteLocation(path=database)

    with (
        serving_lock(location),
        pytest.raises(RemoteAlreadyServedError) as refused,
        serving_lock(location),
    ):
        pass

    assert str(refused.value) == (
        f"Another azathoth remote serve is already serving {database}. "
        "SQLite serves one remote process on one machine. For more than one process, or a "
        "database another machine reaches, use PostgreSQL."
    )
    assert SQLITE_SERVES_ONE_MESSAGE in str(refused.value)


def test_the_lock_is_released_when_serving_stops(
    tmp_path: Path,
) -> None:
    location = SQLiteLocation(path=tmp_path / "azathoth.db")

    with serving_lock(location):
        pass

    with serving_lock(location):
        pass


def test_the_lock_is_released_when_serving_fails(
    tmp_path: Path,
) -> None:
    location = SQLiteLocation(path=tmp_path / "azathoth.db")

    with pytest.raises(RuntimeError), serving_lock(location):
        raise RuntimeError("the server stopped")

    with serving_lock(location):
        pass


def test_servers_of_different_files_do_not_refuse_each_other(
    tmp_path: Path,
) -> None:
    with (
        serving_lock(SQLiteLocation(path=tmp_path / "first.db")),
        serving_lock(SQLiteLocation(path=tmp_path / "second.db")),
    ):
        pass


def test_the_lock_file_is_made_beside_a_database_not_yet_made(
    tmp_path: Path,
) -> None:
    database = tmp_path / "new" / "azathoth.db"

    with serving_lock(SQLiteLocation(path=database)):
        assert serve_lock_path(database).exists()

    assert not database.exists()


def test_a_postgresql_database_takes_no_lock(
    tmp_path: Path,
) -> None:
    with serving_lock(PostgresLocation(URL)), serving_lock(PostgresLocation(URL)):
        pass

    assert list(tmp_path.iterdir()) == []
