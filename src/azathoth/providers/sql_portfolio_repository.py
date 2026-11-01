"""The organizational model portfolio, in either database (ADR 0102)."""

from azathoth.persistence import Database, IntegrityError, Table, require_text
from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)

MODEL_PORTFOLIO_TABLES = (
    Table(
        name="model_portfolio_entries",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                model_portfolio_entries (
                    sequence {sequence},
                    identifier TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                model_portfolio_entries_provider_sequence
            ON model_portfolio_entries (
                provider,
                sequence
            )
            """,
        ),
    ),
)
"""The tables the model portfolio is kept in."""


class SqlModelPortfolioRepository:
    """Persist authorized model portfolio entries in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(MODEL_PORTFOLIO_TABLES)

    def save(
        self,
        entry: ModelPortfolioEntry,
    ) -> None:
        """Persist one entry without replacing existing policy.

        Raises:
            ValueError: An entry with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
                    """
                    INSERT INTO model_portfolio_entries (
                        identifier,
                        provider,
                        model,
                        payload
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entry.identifier,
                        entry.provider,
                        entry.model,
                        entry.model_dump_json(),
                    ),
                )
        except IntegrityError as exc:
            raise ValueError(f"Model portfolio entry {entry.identifier!r} already exists.") from exc

    def get(
        self,
        identifier: str,
    ) -> ModelPortfolioEntry | None:
        """Return one portfolio entry by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM model_portfolio_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def delete(
        self,
        identifier: str,
    ) -> None:
        """Delete one authorized model entry.

        Raises:
            ValueError: The entry does not exist.
        """

        with self._database.transaction() as session:
            deleted = session.execute(
                """
                DELETE FROM model_portfolio_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

        if deleted == 0:
            raise ValueError(f"Model portfolio entry {identifier!r} does not exist.")

    def entries(
        self,
    ) -> tuple[ModelPortfolioEntry, ...]:
        """Return all portfolio entries in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM model_portfolio_entries
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ModelPortfolioEntry:
        """Reconstruct one persisted portfolio entry."""

        return ModelPortfolioEntry.model_validate_json(
            require_text(payload, "Persisted model portfolio entry payload was not text.")
        )


__all__ = [
    "MODEL_PORTFOLIO_TABLES",
    "SqlModelPortfolioRepository",
]
