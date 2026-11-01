"""Production workflow invocations, in either database (ADR 0102)."""

from uuid import UUID

from pydantic import TypeAdapter

from azathoth.persistence import Database, IntegrityError, Table, require_text
from azathoth.workflows.production_invocation import (
    ProductionInvocation,
    ProductionInvocationResult,
)
from azathoth.workflows.production_invocation_repository import (
    IdempotencyKeyInUseError,
)

_RESULT_ADAPTER: TypeAdapter[ProductionInvocationResult] = TypeAdapter(ProductionInvocationResult)

PRODUCTION_INVOCATION_TABLES = (
    Table(
        name="production_invocations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS production_invocations (
                sequence {sequence},
                invocation_id TEXT NOT NULL UNIQUE,
                workflow_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                idempotency_key TEXT,
                request_digest TEXT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                production_invocations_workflow_id_sequence
            ON production_invocations (
                workflow_id,
                sequence
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                production_invocations_idempotency_key
            ON production_invocations (
                idempotency_key
            )
            WHERE idempotency_key IS NOT NULL
            """,
        ),
    ),
    Table(
        name="production_invocation_results",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS production_invocation_results (
                invocation_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                FOREIGN KEY (invocation_id)
                    REFERENCES production_invocations (invocation_id)
            )
            """,
        ),
    ),
)
"""The tables production invocations and their terminal results are kept in."""


class SqlProductionInvocationRepository:
    """Persist production invocations and terminal results in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(PRODUCTION_INVOCATION_TABLES)

    def save(
        self,
        invocation: ProductionInvocation,
    ) -> None:
        """Persist one production invocation without replacing history.

        The idempotency key and request digest are also written to their own
        columns, where a unique index keeps one invocation per key, however
        many processes record invocations at once.

        Raises:
            IdempotencyKeyInUseError: The invocation's idempotency key is
                already recorded on another invocation.
            ValueError: The invocation is already recorded.
        """

        idempotency = invocation.idempotency

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            #
            # The failed insert ended its transaction, so whether the
            # invocation itself was the duplicate is asked in a new one.
            #
            if idempotency is not None and not self._invocation_exists(invocation.id):
                raise IdempotencyKeyInUseError(idempotency.key) from exc

            raise ValueError(f"Production invocation {invocation.id} already exists.") from exc

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocation | None:
        """Return one production invocation by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM production_invocations
                WHERE invocation_id = ?
                """,
                (str(invocation_id),),
            )

        if row is None:
            return None

        return self._deserialize_invocation(row[0])

    def invocation_for_idempotency_key(
        self,
        key: str,
    ) -> ProductionInvocation | None:
        """Return the production invocation recorded under one idempotency key."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM production_invocations
                WHERE idempotency_key = ?
                """,
                (key,),
            )

        if row is None:
            return None

        return self._deserialize_invocation(row[0])

    def invocations(
        self,
    ) -> tuple[ProductionInvocation, ...]:
        """Return all production invocations in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM production_invocations
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_invocation(row[0]) for row in rows)

    def invocations_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[ProductionInvocation, ...]:
        """Return production invocations for one workflow in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM production_invocations
                WHERE workflow_id = ?
                ORDER BY sequence
                """,
                (str(workflow_id),),
            )

        return tuple(self._deserialize_invocation(row[0]) for row in rows)

    def save_result(
        self,
        result: ProductionInvocationResult,
    ) -> None:
        """Persist the single terminal result for one invocation.

        Raises:
            ValueError: The invocation does not exist, or already has a
                terminal result.
        """

        try:
            with self._database.transaction() as session:
                invocation = session.fetchone(
                    """
                    SELECT 1
                    FROM production_invocations
                    WHERE invocation_id = ?
                    """,
                    (str(result.invocation_id),),
                )

                if invocation is None:
                    raise ValueError(
                        f"Production invocation {result.invocation_id} does not exist."
                    )

                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(
                f"Production invocation {result.invocation_id} already has a terminal result."
            ) from exc

    def result(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationResult | None:
        """Return the terminal result for one invocation, if recorded."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM production_invocation_results
                WHERE invocation_id = ?
                """,
                (str(invocation_id),),
            )

        if row is None:
            return None

        return _RESULT_ADAPTER.validate_json(
            require_text(row[0], "Persisted production invocation result payload was not text.")
        )

    def _invocation_exists(
        self,
        invocation_id: UUID,
    ) -> bool:
        """Return whether one invocation is already recorded."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT 1
                FROM production_invocations
                WHERE invocation_id = ?
                """,
                (str(invocation_id),),
            )

        return row is not None

    @staticmethod
    def _deserialize_invocation(
        payload: object,
    ) -> ProductionInvocation:
        """Reconstruct one persisted production invocation."""

        return ProductionInvocation.model_validate_json(
            require_text(payload, "Persisted production invocation payload was not text.")
        )


__all__ = [
    "PRODUCTION_INVOCATION_TABLES",
    "SqlProductionInvocationRepository",
]
