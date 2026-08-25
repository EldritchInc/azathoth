"""SQLite persistence for organizational model portfolio entries."""

import sqlite3
from pathlib import Path

from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)


class SQLiteModelPortfolioRepository:
    """Persist authorized model portfolio entries in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)

        self._initialize()

    def save(
        self,
        entry: ModelPortfolioEntry,
    ) -> None:
        """Persist one entry without replacing existing policy."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
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

                connection.commit()

            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Model portfolio entry {entry.identifier!r} already exists."
                ) from exc

        finally:
            connection.close()

    def get(
        self,
        identifier: str,
    ) -> ModelPortfolioEntry | None:
        """Return one portfolio entry by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM model_portfolio_entries
                WHERE identifier = ?
                """,
                (identifier,),
            ).fetchone()

        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def entries(
        self,
    ) -> tuple[
        ModelPortfolioEntry,
        ...,
    ]:
        """Return all portfolio entries in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM model_portfolio_entries
                ORDER BY sequence
                """
            ).fetchall()

        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ModelPortfolioEntry:
        """Reconstruct one persisted portfolio entry."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted model portfolio entry payload was not text.")

        return ModelPortfolioEntry.model_validate_json(payload)

    def _initialize(
        self,
    ) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS
                    model_portfolio_entries (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        identifier TEXT NOT NULL UNIQUE,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    model_portfolio_entries_provider_sequence
                ON model_portfolio_entries (
                    provider,
                    sequence
                )
                """
            )

            connection.commit()

        finally:
            connection.close()
