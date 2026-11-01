"""Provider model observations, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table, require_text
from azathoth.providers.provider_models import (
    ProviderModelObservation,
)

PROVIDER_MODEL_OBSERVATION_TABLES = (
    Table(
        name="provider_model_observations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                provider_model_observations (
                    sequence {sequence},
                    observation_id TEXT NOT NULL UNIQUE,
                    identifier TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                provider_model_observations_identifier_sequence
            ON provider_model_observations (
                identifier,
                sequence
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                provider_model_observations_provider_sequence
            ON provider_model_observations (
                provider,
                sequence
            )
            """,
        ),
    ),
)
"""The tables provider model observations are kept in."""


class SqlProviderModelObservationRepository:
    """Persist immutable provider model observations in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(PROVIDER_MODEL_OBSERVATION_TABLES)

    def save(
        self,
        observation: ProviderModelObservation,
    ) -> None:
        """Persist one observation without replacing existing evidence.

        Raises:
            ValueError: An observation with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
                    """
                    INSERT INTO provider_model_observations (
                        observation_id,
                        identifier,
                        provider,
                        model,
                        fingerprint,
                        observed_at,
                        payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(observation.id),
                        observation.identifier,
                        observation.provider,
                        observation.model_identifier,
                        observation.fingerprint,
                        observation.observed_at.isoformat(),
                        observation.model_dump_json(),
                    ),
                )
        except IntegrityError as exc:
            raise ValueError(
                f"Provider model observation {observation.id} already exists."
            ) from exc

    def get(
        self,
        observation_id: UUID,
    ) -> ProviderModelObservation | None:
        """Return one observation by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM provider_model_observations
                WHERE observation_id = ?
                """,
                (str(observation_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def observations(
        self,
    ) -> tuple[ProviderModelObservation, ...]:
        """Return all observations in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM provider_model_observations
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def observations_for_model(
        self,
        identifier: str,
    ) -> tuple[ProviderModelObservation, ...]:
        """Return observations for one model in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM provider_model_observations
                WHERE identifier = ?
                ORDER BY sequence
                """,
                (identifier,),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def latest(
        self,
        identifier: str,
    ) -> ProviderModelObservation | None:
        """Return the latest persisted observation for one model."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM provider_model_observations
                WHERE identifier = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (identifier,),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ProviderModelObservation:
        """Reconstruct one persisted provider model observation."""

        return ProviderModelObservation.model_validate_json(
            require_text(payload, "Persisted provider model observation payload was not text.")
        )


__all__ = [
    "PROVIDER_MODEL_OBSERVATION_TABLES",
    "SqlProviderModelObservationRepository",
]
