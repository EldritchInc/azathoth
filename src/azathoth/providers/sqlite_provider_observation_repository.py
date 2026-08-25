"""SQLite persistence for provider model observations."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.providers.provider_models import (
    ProviderModelObservation,
)


class SQLiteProviderModelObservationRepository:
    """Persist immutable provider model observations in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(
            database
        )

        self._initialize()

    def save(
        self,
        observation: ProviderModelObservation,
    ) -> None:
        """Persist one observation without replacing existing evidence."""

        connection = sqlite3.connect(
            self._database
        )

        try:
            try:
                connection.execute(
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
                        str(
                            observation.id
                        ),
                        observation.identifier,
                        observation.provider,
                        observation.model_identifier,
                        observation.fingerprint,
                        observation.observed_at.isoformat(),
                        observation.model_dump_json(),
                    ),
                )

                connection.commit()

            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "Provider model observation "
                    f"{observation.id} already exists."
                ) from exc

        finally:
            connection.close()

    def get(
        self,
        observation_id: UUID,
    ) -> ProviderModelObservation | None:
        """Return one observation by identifier."""

        connection = sqlite3.connect(
            self._database
        )

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM provider_model_observations
                WHERE observation_id = ?
                """,
                (
                    str(
                        observation_id
                    ),
                ),
            ).fetchone()

        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(
            row[0]
        )

    def observations(
        self,
    ) -> tuple[
        ProviderModelObservation,
        ...,
    ]:
        """Return all observations in insertion order."""

        connection = sqlite3.connect(
            self._database
        )

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM provider_model_observations
                ORDER BY sequence
                """
            ).fetchall()

        finally:
            connection.close()

        return tuple(
            self._deserialize_payload(
                row[0]
            )
            for row in rows
        )

    def observations_for_model(
        self,
        identifier: str,
    ) -> tuple[
        ProviderModelObservation,
        ...,
    ]:
        """Return observations for one model in insertion order."""

        connection = sqlite3.connect(
            self._database
        )

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM provider_model_observations
                WHERE identifier = ?
                ORDER BY sequence
                """,
                (
                    identifier,
                ),
            ).fetchall()

        finally:
            connection.close()

        return tuple(
            self._deserialize_payload(
                row[0]
            )
            for row in rows
        )

    def latest(
        self,
        identifier: str,
    ) -> ProviderModelObservation | None:
        """Return the latest persisted observation for one model."""

        connection = sqlite3.connect(
            self._database
        )

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM provider_model_observations
                WHERE identifier = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (
                    identifier,
                ),
            ).fetchone()

        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(
            row[0]
        )

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ProviderModelObservation:
        """Reconstruct one persisted provider model observation."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError(
                "Persisted provider model observation "
                "payload was not text."
            )

        return ProviderModelObservation.model_validate_json(
            payload
        )

    def _initialize(
        self,
    ) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(
            self._database
        )

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS
                    provider_model_observations (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        observation_id TEXT NOT NULL UNIQUE,
                        identifier TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        observed_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    provider_model_observations_identifier_sequence
                ON provider_model_observations (
                    identifier,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    provider_model_observations_provider_sequence
                ON provider_model_observations (
                    provider,
                    sequence
                )
                """
            )

            connection.commit()

        finally:
            connection.close()
