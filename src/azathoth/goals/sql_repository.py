"""Reusable goals, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.goals.models import Goal
from azathoth.persistence import Database, IntegrityError, Table, require_text

GOAL_TABLES = (
    Table(
        name="goals",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS goals (
                sequence {sequence},
                goal_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                goals_name_sequence
            ON goals (
                name,
                sequence
            )
            """,
        ),
    ),
)
"""The tables goals are kept in."""


class SqlGoalRepository:
    """Persist immutable goals in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(GOAL_TABLES)

    def save(
        self,
        goal: Goal,
    ) -> None:
        """Persist one goal without replacing existing configuration.

        Raises:
            ValueError: A goal with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(f"Goal {goal.id} already exists.") from exc

    def get(
        self,
        goal_id: UUID,
    ) -> Goal | None:
        """Return one goal by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM goals
                WHERE goal_id = ?
                """,
                (str(goal_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def goals(
        self,
    ) -> tuple[Goal, ...]:
        """Return all goals in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM goals
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> Goal:
        """Reconstruct one persisted goal."""

        return Goal.model_validate_json(
            require_text(payload, "Persisted goal payload was not text.")
        )


__all__ = [
    "GOAL_TABLES",
    "SqlGoalRepository",
]
