"""Tests for the content-addressed input store (ADR 0096)."""

import hashlib
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from azathoth.inputs import (
    ContentStore,
    InMemoryContentStore,
    SQLiteContentStore,
    content_bytes_digest,
)
from azathoth.revisions import CONTENT_DIGEST_PATTERN

CHAPTER = b"Mara climbed the stairs of Saint Elmo's Light.\n"

OTHER = b'{"chapters": 3}'

StoreFactory = Callable[[Path], ContentStore]


def in_memory(
    _tmp_path: Path,
) -> ContentStore:
    """Return an empty in-memory store."""

    return InMemoryContentStore()


def sqlite(
    tmp_path: Path,
) -> ContentStore:
    """Return a SQLite store in a fresh database."""

    return SQLiteContentStore(tmp_path / "azathoth.db")


STORES = [
    pytest.param(in_memory, id="memory"),
    pytest.param(sqlite, id="sqlite"),
]


def test_digest_is_the_sha256_hex_of_the_bytes() -> None:
    digest = content_bytes_digest(CHAPTER)

    assert digest == hashlib.sha256(CHAPTER).hexdigest()
    assert len(digest) == 64
    assert digest == digest.lower()


def test_digest_matches_the_revision_digest_format() -> None:
    assert re.match(CONTENT_DIGEST_PATTERN, content_bytes_digest(b"")) is not None


@pytest.mark.parametrize("factory", STORES)
def test_put_returns_the_content_digest(
    factory: StoreFactory,
    tmp_path: Path,
) -> None:
    assert factory(tmp_path).put(CHAPTER) == content_bytes_digest(CHAPTER)


@pytest.mark.parametrize("factory", STORES)
def test_get_returns_the_stored_bytes(
    factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = factory(tmp_path)

    digest = store.put(CHAPTER)

    assert store.get(digest) == CHAPTER
    assert store.contains(digest)


@pytest.mark.parametrize("factory", STORES)
def test_unknown_digests_are_absent(
    factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = factory(tmp_path)

    digest = content_bytes_digest(OTHER)

    assert store.get(digest) is None
    assert not store.contains(digest)


@pytest.mark.parametrize("factory", STORES)
def test_empty_content_can_be_stored(
    factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = factory(tmp_path)

    digest = store.put(b"")

    assert store.get(digest) == b""


@pytest.mark.parametrize("factory", STORES)
def test_putting_the_same_content_twice_is_harmless(
    factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = factory(tmp_path)

    first = store.put(CHAPTER)
    second = store.put(CHAPTER)

    assert first == second
    assert store.get(first) == CHAPTER


@pytest.mark.parametrize("factory", STORES)
def test_distinct_content_is_kept_apart(
    factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = factory(tmp_path)

    chapter = store.put(CHAPTER)
    other = store.put(OTHER)

    assert chapter != other
    assert store.get(chapter) == CHAPTER
    assert store.get(other) == OTHER


def test_sqlite_store_keeps_content_across_instances(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    digest = SQLiteContentStore(database).put(CHAPTER)

    assert SQLiteContentStore(database).get(digest) == CHAPTER


def test_sqlite_store_keeps_identical_content_once(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"
    store = SQLiteContentStore(database)

    store.put(CHAPTER)
    store.put(CHAPTER)
    store.put(OTHER)

    connection = sqlite3.connect(database)

    try:
        rows = connection.execute(
            "SELECT digest, size_bytes FROM content_blobs ORDER BY size_bytes",
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        (content_bytes_digest(OTHER), len(OTHER)),
        (content_bytes_digest(CHAPTER), len(CHAPTER)),
    ]


def test_sqlite_store_creates_its_table_in_an_existing_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    connection = sqlite3.connect(database)

    try:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.commit()
    finally:
        connection.close()

    store = SQLiteContentStore(database)

    assert store.get(store.put(OTHER)) == OTHER


def test_stores_satisfy_the_protocol(
    tmp_path: Path,
) -> None:
    assert isinstance(InMemoryContentStore(), ContentStore)
    assert isinstance(SQLiteContentStore(tmp_path / "azathoth.db"), ContentStore)
