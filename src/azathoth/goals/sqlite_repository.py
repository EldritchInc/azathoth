"""SQLite persistence for reusable goals."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.goals.models import Goal


class SQLiteGoalRepository:
    """Persist immutable goals in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        goal: Goal,
    ) -> None:
        """Persist one goal without replacing existing configuration."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO goals (
                        goal_id,
                        name,
                        payload
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(goal.id),
                        goal.name,
                        goal.model_dump_json(),
                    ),
                )

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Goal {goal.id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        goal_id: UUID,
    ) -> Goal | None:
        """Return one goal by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM goals
                WHERE goal_id = ?
                """,
                (str(goal_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def goals(
        self,
    ) -> tuple[Goal, ...]:
        """Return all goals in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM goals
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> Goal:
        """Reconstruct one persisted goal."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted goal payload was not text.")

        return Goal.model_validate_json(payload)

    def _initialize(
        self,
    ) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    goals_name_sequence
                ON goals (
                    name,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()
