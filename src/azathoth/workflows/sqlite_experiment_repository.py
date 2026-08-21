"""SQLite persistence for durable workflow experiment records."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.experiment_record import (
    WorkflowExperimentRecord,
)


class SQLiteWorkflowExperimentRepository:
    """Persist immutable workflow experiment records in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        experiment: WorkflowExperimentRecord,
    ) -> None:
        """Persist one experiment without replacing existing evidence."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_experiments (
                        experiment_id,
                        payload
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(experiment.id),
                        experiment.model_dump_json(),
                    ),
                )

                for observation in experiment.observations:
                    connection.execute(
                        """
                        INSERT INTO workflow_experiment_observations (
                            experiment_id,
                            workflow_id,
                            run_id,
                            evaluation_id
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            str(experiment.id),
                            str(observation.workflow.id),
                            str(observation.run_id),
                            str(observation.evaluation_id),
                        ),
                    )

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Workflow experiment {experiment.id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        experiment_id: UUID,
    ) -> WorkflowExperimentRecord | None:
        """Return one experiment by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_experiments
                WHERE experiment_id = ?
                """,
                (str(experiment_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def experiments(
        self,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return all experiments in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_experiments
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def experiments_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return experiments containing one workflow."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT experiment.payload
                FROM workflow_experiments AS experiment
                JOIN workflow_experiment_observations AS observation
                    ON observation.experiment_id = experiment.experiment_id
                WHERE observation.workflow_id = ?
                GROUP BY experiment.experiment_id
                ORDER BY experiment.sequence
                """,
                (str(workflow_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowExperimentRecord:
        """Reconstruct one persisted workflow experiment."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted workflow experiment payload was not text.")

        return WorkflowExperimentRecord.model_validate_json(payload)

    def _initialize(self) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_experiments (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_experiment_observations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    evaluation_id TEXT NOT NULL,
                    UNIQUE (
                        experiment_id,
                        run_id
                    )
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_experiment_observations_workflow_id
                ON workflow_experiment_observations (
                    workflow_id,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_experiment_observations_run_id
                ON workflow_experiment_observations (
                    run_id,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_experiment_observations_evaluation_id
                ON workflow_experiment_observations (
                    evaluation_id,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()
