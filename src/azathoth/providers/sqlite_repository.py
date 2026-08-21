"""SQLite persistence for configured language model metadata."""

import sqlite3
from pathlib import Path

from azathoth.providers.models import ModelMetadata


class SQLiteModelRepository:
    """Persist immutable model metadata in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        model: ModelMetadata,
    ) -> None:
        """Persist one model without replacing existing configuration."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO models (
                        identifier,
                        provider,
                        payload
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        model.identifier,
                        model.provider,
                        model.model_dump_json(),
                    ),
                )

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Model {model.identifier!r} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        identifier: str,
    ) -> ModelMetadata | None:
        """Return one configured model by provider-qualified identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM models
                WHERE identifier = ?
                """,
                (identifier,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def models(
        self,
    ) -> tuple[ModelMetadata, ...]:
        """Return all configured models in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM models
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def models_for_provider(
        self,
        provider: str,
    ) -> tuple[ModelMetadata, ...]:
        """Return configured models belonging to one provider."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM models
                WHERE provider = ?
                ORDER BY sequence
                """,
                (provider,),
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ModelMetadata:
        """Reconstruct one persisted model metadata record."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted model metadata payload was not text.")

        return ModelMetadata.model_validate_json(payload)

    def _initialize(
        self,
    ) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS models (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    models_provider_sequence
                ON models (
                    provider,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()
