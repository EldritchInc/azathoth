"""Configured language model metadata, in either database (ADR 0102)."""

from azathoth.persistence import Database, IntegrityError, Table, require_text
from azathoth.providers.models import ModelMetadata

MODEL_TABLES = (
    Table(
        name="models",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS models (
                sequence {sequence},
                identifier TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                models_provider_sequence
            ON models (
                provider,
                sequence
            )
            """,
        ),
    ),
)
"""The tables configured models are kept in."""


class SqlModelRepository:
    """Persist immutable model metadata in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(MODEL_TABLES)

    def save(
        self,
        model: ModelMetadata,
    ) -> None:
        """Persist one model without replacing existing configuration.

        Raises:
            ValueError: A model with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(f"Model {model.identifier!r} already exists.") from exc

    def get(
        self,
        identifier: str,
    ) -> ModelMetadata | None:
        """Return one configured model by provider-qualified identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM models
                WHERE identifier = ?
                """,
                (identifier,),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def models(
        self,
    ) -> tuple[ModelMetadata, ...]:
        """Return all configured models in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM models
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def models_for_provider(
        self,
        provider: str,
    ) -> tuple[ModelMetadata, ...]:
        """Return configured models belonging to one provider."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM models
                WHERE provider = ?
                ORDER BY sequence
                """,
                (provider,),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ModelMetadata:
        """Reconstruct one persisted model metadata record."""

        return ModelMetadata.model_validate_json(
            require_text(payload, "Persisted model metadata payload was not text.")
        )


__all__ = [
    "MODEL_TABLES",
    "SqlModelRepository",
]
