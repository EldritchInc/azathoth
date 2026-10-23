"""SQLite persistence for the semantic judge rotation."""

import sqlite3
from pathlib import Path

from azathoth.evaluation.judges import (
    JudgeEntry,
    JudgeRotation,
)


class SQLiteJudgeRotationRepository:
    """Persist the semantic judge rotation in SQLite, in insertion order."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)

        self._initialize()

    def add(
        self,
        entry: JudgeEntry,
    ) -> None:
        """Append one judge to the end of the rotation.

        Raises:
            ValueError: The judge is already in the rotation.
        """

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO judge_rotation_entries (
                        identifier,
                        payload
                    )
                    VALUES (?, ?)
                    """,
                    (
                        entry.identifier,
                        entry.model_dump_json(),
                    ),
                )

                connection.commit()

            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Judge {entry.identifier!r} is already in the rotation.") from exc

        finally:
            connection.close()

    def get(
        self,
        identifier: str,
    ) -> JudgeEntry | None:
        """Return one judge by provider-qualified identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM judge_rotation_entries
                WHERE identifier = ?
                """,
                (identifier,),
            ).fetchone()

        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def remove(
        self,
        identifier: str,
    ) -> None:
        """Remove one judge from the rotation.

        Raises:
            ValueError: The judge is not in the rotation.
        """

        connection = sqlite3.connect(self._database)

        try:
            cursor = connection.execute(
                """
                DELETE FROM judge_rotation_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Judge {identifier!r} is not in the rotation.")

            connection.commit()

        finally:
            connection.close()

    def rotation(
        self,
    ) -> JudgeRotation:
        """Return every judge in the order they were added."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM judge_rotation_entries
                ORDER BY sequence
                """
            ).fetchall()

        finally:
            connection.close()

        return JudgeRotation(
            entries=tuple(self._deserialize_payload(row[0]) for row in rows),
        )

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> JudgeEntry:
        """Reconstruct one persisted judge."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted judge rotation entry payload was not text.")

        return JudgeEntry.model_validate_json(payload)

    def _initialize(
        self,
    ) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS
                    judge_rotation_entries (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        identifier TEXT NOT NULL UNIQUE,
                        payload TEXT NOT NULL
                    )
                """
            )

            connection.commit()

        finally:
            connection.close()
