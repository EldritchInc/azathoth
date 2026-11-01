"""Content-addressed storage for resolved input content (ADR 0096)."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from azathoth.persistence import Database, SQLiteDatabase, Table


def content_bytes_digest(
    content: bytes,
) -> str:
    """Return the lowercase hex SHA-256 digest of some content.

    It has the same form as the content digests of revisioned documents.
    """

    return hashlib.sha256(content).hexdigest()


@runtime_checkable
class ContentStore(Protocol):
    """Keep content by the digest of its bytes.

    Content is immutable: a digest always names the same bytes, so storing
    the same content again changes nothing.
    """

    def put(
        self,
        content: bytes,
    ) -> str:
        """Store content, if it is not already stored, and return its digest."""
        ...

    def get(
        self,
        digest: str,
    ) -> bytes | None:
        """Return the content with one digest, or None when it is not stored."""
        ...

    def contains(
        self,
        digest: str,
    ) -> bool:
        """Return whether content with one digest is stored."""
        ...


class InMemoryContentStore:
    """Keep content in process memory."""

    def __init__(self) -> None:
        self._content: dict[str, bytes] = {}

    def put(
        self,
        content: bytes,
    ) -> str:
        """Store content, if it is not already stored, and return its digest."""

        digest = content_bytes_digest(content)

        self._content.setdefault(digest, bytes(content))

        return digest

    def get(
        self,
        digest: str,
    ) -> bytes | None:
        """Return the content with one digest, or None when it is not stored."""

        return self._content.get(digest)

    def contains(
        self,
        digest: str,
    ) -> bool:
        """Return whether content with one digest is stored."""

        return digest in self._content


CONTENT_TABLES = (
    Table(
        name="content_blobs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS content_blobs (
                digest TEXT PRIMARY KEY,
                size_bytes INTEGER NOT NULL,
                content {blob} NOT NULL,
                stored_at TEXT NOT NULL
            )
            """,
        ),
    ),
)
"""The tables stored content is kept in."""


class SqlContentStore:
    """Keep content in the `content_blobs` table of a database (ADR 0102).

    Each row holds one digest, its content's size, the content, and when it
    was first stored. Identical content is stored once, however many
    processes store it at once.
    """

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(CONTENT_TABLES)

    def put(
        self,
        content: bytes,
    ) -> str:
        """Store content, if it is not already stored, and return its digest."""

        digest = content_bytes_digest(content)

        with self._database.transaction() as session:
            session.execute(
                """
                INSERT INTO content_blobs (
                    digest,
                    size_bytes,
                    content,
                    stored_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (digest) DO NOTHING
                """,
                (
                    digest,
                    len(content),
                    bytes(content),
                    datetime.now(UTC).isoformat(),
                ),
            )

        return digest

    def get(
        self,
        digest: str,
    ) -> bytes | None:
        """Return the content with one digest, or None when it is not stored."""

        with self._database.transaction() as session:
            row = session.fetchone(
                "SELECT content FROM content_blobs WHERE digest = ?",
                (digest,),
            )

        if row is None:
            return None

        content = row[0]

        if not isinstance(content, bytes | bytearray | memoryview):
            raise TypeError(f"Stored content {digest} was not bytes.")

        return bytes(content)

    def contains(
        self,
        digest: str,
    ) -> bool:
        """Return whether content with one digest is stored."""

        with self._database.transaction() as session:
            row = session.fetchone(
                "SELECT 1 FROM content_blobs WHERE digest = ?",
                (digest,),
            )

        return row is not None


class SQLiteContentStore(SqlContentStore):
    """Keep content in the `content_blobs` table of a SQLite database.

    Each row holds one digest, its content's size, the content, and when it
    was first stored. Identical content is stored once.
    """

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))


__all__ = [
    "CONTENT_TABLES",
    "ContentStore",
    "InMemoryContentStore",
    "SQLiteContentStore",
    "SqlContentStore",
    "content_bytes_digest",
]
