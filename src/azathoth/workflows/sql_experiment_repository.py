"""Durable workflow experiment records, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table
from azathoth.workflows.experiment_record import (
    WorkflowExperimentRecord,
)

WORKFLOW_EXPERIMENT_TABLES = (
    Table(
        name="workflow_experiments",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_experiments (
                sequence {sequence},
                experiment_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            )
            """,
        ),
    ),
    Table(
        name="workflow_experiment_observations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_experiment_observations (
                sequence {sequence},
                experiment_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                evaluation_id TEXT NOT NULL,
                UNIQUE (
                    experiment_id,
                    run_id
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_experiment_observations_workflow_id
            ON workflow_experiment_observations (
                workflow_id,
                sequence
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_experiment_observations_run_id
            ON workflow_experiment_observations (
                run_id,
                sequence
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_experiment_observations_evaluation_id
            ON workflow_experiment_observations (
                evaluation_id,
                sequence
            )
            """,
        ),
    ),
)
"""The tables workflow experiments, and the index of what they observed, are kept in."""


class SqlWorkflowExperimentRepository:
    """Persist immutable workflow experiment records in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(WORKFLOW_EXPERIMENT_TABLES)

    def save(
        self,
        experiment: WorkflowExperimentRecord,
    ) -> None:
        """Persist one experiment without replacing existing evidence.

        Every case of every observation is indexed by workflow, run, and
        evaluation, so experiments can be found by the workflows they observed.
        The record and its index are written in one transaction.

        Raises:
            ValueError: An experiment with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
                    for case in observation.cases:
                        session.execute(
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
                                str(case.run_id),
                                str(case.evaluation_id),
                            ),
                        )
        except IntegrityError as exc:
            raise ValueError(f"Workflow experiment {experiment.id} already exists.") from exc

    def get(
        self,
        experiment_id: UUID,
    ) -> WorkflowExperimentRecord | None:
        """Return one experiment by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_experiments
                WHERE experiment_id = ?
                """,
                (str(experiment_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def experiments(
        self,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return all experiments in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_experiments
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def experiments_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowExperimentRecord, ...]:
        """Return experiments containing one workflow, in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT experiment.payload
                FROM workflow_experiments AS experiment
                WHERE EXISTS (
                    SELECT 1
                    FROM workflow_experiment_observations AS observation
                    WHERE observation.experiment_id = experiment.experiment_id
                        AND observation.workflow_id = ?
                )
                ORDER BY experiment.sequence
                """,
                (str(workflow_id),),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowExperimentRecord:
        """Reconstruct one persisted workflow experiment."""

        if not isinstance(payload, str):
            raise TypeError("Persisted workflow experiment payload was not text.")

        return WorkflowExperimentRecord.model_validate_json(payload)


__all__ = [
    "WORKFLOW_EXPERIMENT_TABLES",
    "SqlWorkflowExperimentRepository",
]
