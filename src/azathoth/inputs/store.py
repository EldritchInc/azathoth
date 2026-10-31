"""Content-addressed storage for resolved input content (ADR 0096)."""

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


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


class SQLiteContentStore:
    """Keep content in the `content_blobs` table of a SQLite database.

    Each row holds one digest, its content's size, the content, and when it
    was first stored. Identical content is stored once.
    """

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def put(
        self,
        content: bytes,
    ) -> str:
        """Store content, if it is not already stored, and return its digest."""

        digest = content_bytes_digest(content)

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
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
                    sqlite3.Binary(content),
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return digest

    def get(
        self,
        digest: str,
    ) -> bytes | None:
        """Return the content with one digest, or None when it is not stored."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                "SELECT content FROM content_blobs WHERE digest = ?",
                (digest,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return bytes(row[0])

    def contains(
        self,
        digest: str,
    ) -> bool:
        """Return whether content with one digest is stored."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                "SELECT 1 FROM content_blobs WHERE digest = ?",
                (digest,),
            ).fetchone()
        finally:
            connection.close()

        return row is not None

    def _initialize(self) -> None:
        """Create the content table."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS content_blobs (
                    digest TEXT PRIMARY KEY,
                    size_bytes INTEGER NOT NULL,
                    content BLOB NOT NULL,
                    stored_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()


__all__ = [
    "ContentStore",
    "InMemoryContentStore",
    "SQLiteContentStore",
    "content_bytes_digest",
]
