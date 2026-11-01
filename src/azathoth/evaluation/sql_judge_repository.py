"""The semantic judge rotation, in either database (ADR 0102)."""

from azathoth.evaluation.judges import (
    JudgeEntry,
    JudgeRotation,
)
from azathoth.persistence import Database, IntegrityError, Table, require_text

JUDGE_ROTATION_TABLES = (
    Table(
        name="judge_rotation_entries",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                judge_rotation_entries (
                    sequence {sequence},
                    identifier TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )
            """,
        ),
    ),
)
"""The tables the judge rotation is kept in."""


class SqlJudgeRotationRepository:
    """Persist the semantic judge rotation in a database, in insertion order."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(JUDGE_ROTATION_TABLES)

    def add(
        self,
        entry: JudgeEntry,
    ) -> None:
        """Append one judge to the end of the rotation.

        Raises:
            ValueError: The judge is already in the rotation.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(f"Judge {entry.identifier!r} is already in the rotation.") from exc

    def get(
        self,
        identifier: str,
    ) -> JudgeEntry | None:
        """Return one judge by provider-qualified identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM judge_rotation_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

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

        with self._database.transaction() as session:
            removed = session.execute(
                """
                DELETE FROM judge_rotation_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

        if removed == 0:
            raise ValueError(f"Judge {identifier!r} is not in the rotation.")

    def rotation(
        self,
    ) -> JudgeRotation:
        """Return every judge in the order they were added."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM judge_rotation_entries
                ORDER BY sequence
                """
            )

        return JudgeRotation(
            entries=tuple(self._deserialize_payload(row[0]) for row in rows),
        )

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> JudgeEntry:
        """Reconstruct one persisted judge."""

        return JudgeEntry.model_validate_json(
            require_text(payload, "Persisted judge rotation entry payload was not text.")
        )


__all__ = [
    "JUDGE_ROTATION_TABLES",
    "SqlJudgeRotationRepository",
]
