"""SQLite persistence for production workflow invocations."""

import sqlite3
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter

from azathoth.workflows.production_invocation import (
    ProductionInvocation,
    ProductionInvocationResult,
)
from azathoth.workflows.production_invocation_repository import (
    IdempotencyKeyInUseError,
)

_RESULT_ADAPTER: TypeAdapter[ProductionInvocationResult] = TypeAdapter(ProductionInvocationResult)

_IDEMPOTENCY_COLUMNS = (
    "idempotency_key",
    "request_digest",
)


class SQLiteProductionInvocationRepository:
    """Persist production invocations and terminal results in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        invocation: ProductionInvocation,
    ) -> None:
        """Persist one production invocation without replacing history.

        The idempotency key and request digest are also written to their own
        columns, where a unique index keeps one invocation per key.

        Raises:
            IdempotencyKeyInUseError: The invocation's idempotency key is
                already recorded on another invocation.
            ValueError: The invocation is already recorded.
        """

        idempotency = invocation.idempotency

        connection = sqlite3.connect(
            self._database,
        )

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO production_invocations (
                        invocation_id,
                        workflow_id,
                        payload,
                        idempotency_key,
                        request_digest
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(invocation.id),
                        str(invocation.workflow_id),
                        invocation.model_dump_json(),
                        idempotency.key if idempotency is not None else None,
                        idempotency.request_digest if idempotency is not None else None,
                    ),
                )

                connection.commit()
            except sqlite3.IntegrityError as exc:
                if idempotency is not None and not self._invocation_exists(
                    connection,
                    invocation.id,
                ):
                    raise IdempotencyKeyInUseError(idempotency.key) from exc

                raise ValueError(f"Production invocation {invocation.id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocation | None:
        """Return one production invocation by identifier."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM production_invocations
                WHERE invocation_id = ?
                """,
                (str(invocation_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_invocation(
            row[0],
        )

    def invocation_for_idempotency_key(
        self,
        key: str,
    ) -> ProductionInvocation | None:
        """Return the production invocation recorded under one idempotency key."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM production_invocations
                WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_invocation(
            row[0],
        )

    def invocations(
        self,
    ) -> tuple[ProductionInvocation, ...]:
        """Return all production invocations in insertion order."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM production_invocations
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_invocation(row[0]) for row in rows)

    def invocations_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[ProductionInvocation, ...]:
        """Return production invocations for one workflow in insertion order."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM production_invocations
                WHERE workflow_id = ?
                ORDER BY sequence
                """,
                (str(workflow_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_invocation(row[0]) for row in rows)

    def save_result(
        self,
        result: ProductionInvocationResult,
    ) -> None:
        """Persist the single terminal result for one invocation."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            invocation = connection.execute(
                """
                SELECT 1
                FROM production_invocations
                WHERE invocation_id = ?
                """,
                (str(result.invocation_id),),
            ).fetchone()

            if invocation is None:
                raise ValueError(f"Production invocation {result.invocation_id} does not exist.")

            try:
                connection.execute(
                    """
                    INSERT INTO production_invocation_results (
                        invocation_id,
                        payload
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(result.invocation_id),
                        _RESULT_ADAPTER.dump_json(result).decode(),
                    ),
                )

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Production invocation {result.invocation_id} already has a terminal result."
                ) from exc
        finally:
            connection.close()

    def result(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationResult | None:
        """Return the terminal result for one invocation, if recorded."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM production_invocation_results
                WHERE invocation_id = ?
                """,
                (str(invocation_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_result(
            row[0],
        )

    @staticmethod
    def _invocation_exists(
        connection: sqlite3.Connection,
        invocation_id: UUID,
    ) -> bool:
        """Return whether one invocation is already recorded."""

        row = connection.execute(
            """
            SELECT 1
            FROM production_invocations
            WHERE invocation_id = ?
            """,
            (str(invocation_id),),
        ).fetchone()

        return row is not None

    @staticmethod
    def _deserialize_invocation(
        payload: object,
    ) -> ProductionInvocation:
        """Reconstruct one persisted production invocation."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted production invocation payload was not text.")

        return ProductionInvocation.model_validate_json(
            payload,
        )

    @staticmethod
    def _deserialize_result(
        payload: object,
    ) -> ProductionInvocationResult:
        """Reconstruct one persisted terminal invocation result."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted production invocation result payload was not text.")

        return _RESULT_ADAPTER.validate_json(
            payload,
        )

    def _initialize(
        self,
    ) -> None:
        """Create repository tables and migrate earlier invocation schemas.

        A table from before ADR 0097 gains the idempotency columns in place,
        keeping every invocation and its sequence.
        """

        connection = sqlite3.connect(
            self._database,
        )

        try:
            if self._requires_revision_column_migration(
                connection,
            ):
                self._migrate_revision_column(
                    connection,
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS production_invocations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    invocation_id TEXT NOT NULL UNIQUE,
                    workflow_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    idempotency_key TEXT,
                    request_digest TEXT
                )
                """
            )

            self._add_missing_idempotency_columns(
                connection,
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    production_invocations_workflow_id_sequence
                ON production_invocations (
                    workflow_id,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    production_invocations_idempotency_key
                ON production_invocations (
                    idempotency_key
                )
                WHERE idempotency_key IS NOT NULL
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS production_invocation_results (
                    invocation_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    FOREIGN KEY (invocation_id)
                        REFERENCES production_invocations (invocation_id)
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _add_missing_idempotency_columns(
        connection: sqlite3.Connection,
    ) -> None:
        """Add the idempotency columns an earlier invocation table lacks."""

        columns = {
            row[1]
            for row in connection.execute(
                """
                PRAGMA table_info(production_invocations)
                """
            ).fetchall()
        }

        for column in _IDEMPOTENCY_COLUMNS:
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE production_invocations ADD COLUMN {column} TEXT",
                )

    @staticmethod
    def _requires_revision_column_migration(
        connection: sqlite3.Connection,
    ) -> bool:
        """Return whether the invocation table retains obsolete revision identity."""

        columns = connection.execute(
            """
            PRAGMA table_info(production_invocations)
            """
        ).fetchall()

        return any(row[1] == "production_revision_id" for row in columns)

    @staticmethod
    def _migrate_revision_column(
        connection: sqlite3.Connection,
    ) -> None:
        """Remove obsolete revision identity while preserving invocation history."""

        connection.execute(
            """
            ALTER TABLE production_invocations
            RENAME TO production_invocations_with_revision
            """
        )

        connection.execute(
            """
            CREATE TABLE production_invocations (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                invocation_id TEXT NOT NULL UNIQUE,
                workflow_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            INSERT INTO production_invocations (
                sequence,
                invocation_id,
                workflow_id,
                payload
            )
            SELECT
                sequence,
                invocation_id,
                workflow_id,
                payload
            FROM production_invocations_with_revision
            ORDER BY sequence
            """
        )

        connection.execute(
            """
            DROP TABLE production_invocations_with_revision
            """
        )
