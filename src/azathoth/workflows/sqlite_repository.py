"""SQLite persistence for durable workflow specifications."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.models import WorkflowSpecification


class SQLiteWorkflowRepository:
    """Persist workflow specifications in a SQLite database."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        specification: WorkflowSpecification,
    ) -> None:
        """Persist one workflow specification without replacing existing data."""

        workflow_id = specification.metadata.id

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_specifications (
                        workflow_id,
                        payload
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(workflow_id),
                        specification.model_dump_json(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Workflow specification {workflow_id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecification | None:
        """Return a workflow specification by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_specifications
                WHERE workflow_id = ?
                """,
                (str(workflow_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        payload = row[0]

        if not isinstance(payload, str):
            raise TypeError(f"Persisted workflow payload for {workflow_id} was not text.")

        return WorkflowSpecification.model_validate_json(payload)

    def specifications(
        self,
    ) -> tuple[WorkflowSpecification, ...]:
        """Return all persisted workflow specifications in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_specifications
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        specifications: list[WorkflowSpecification] = []

        for row in rows:
            payload = row[0]

            if not isinstance(payload, str):
                raise TypeError("Persisted workflow specification payload was not text.")

            specifications.append(WorkflowSpecification.model_validate_json(payload))

        return tuple(specifications)

    def _initialize(self) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_specifications (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()
