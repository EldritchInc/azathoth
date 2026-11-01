"""Every repository of one database, composed in one place (ADR 0102).

This module imports Azathoth's domain packages, which import
`azathoth.persistence` themselves, so `azathoth.persistence` does not import
it: import it as `azathoth.persistence.repositories`.
"""

from functools import cached_property
from pathlib import Path
from typing import Final

from azathoth.evaluation import (
    BENCHMARK_TABLES,
    JUDGE_ROTATION_TABLES,
    BenchmarkRepository,
    JudgeRotationRepository,
    SqlBenchmarkRepository,
    SQLiteBenchmarkRepository,
    SQLiteJudgeRotationRepository,
    SqlJudgeRotationRepository,
)
from azathoth.goals import GOAL_TABLES, GoalRepository, SqlGoalRepository, SQLiteGoalRepository
from azathoth.inputs import CONTENT_TABLES, ContentStore, SqlContentStore, SQLiteContentStore
from azathoth.persistence.database import Database, Table
from azathoth.persistence.location import (
    DatabaseLocation,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
)
from azathoth.persistence.postgres import PostgresDatabase
from azathoth.persistence.sqlite import SQLiteDatabase
from azathoth.providers import (
    MODEL_PORTFOLIO_TABLES,
    MODEL_TABLES,
    PROVIDER_MODEL_OBSERVATION_TABLES,
    ModelPortfolioRepository,
    ModelRepository,
    ProviderModelObservationRepository,
    SQLiteModelPortfolioRepository,
    SQLiteModelRepository,
    SQLiteProviderModelObservationRepository,
    SqlModelPortfolioRepository,
    SqlModelRepository,
    SqlProviderModelObservationRepository,
)
from azathoth.tools import TOOL_TABLES, SQLiteToolRepository, SqlToolRepository, ToolRepository
from azathoth.workflows import (
    PRODUCTION_INVOCATION_RUN_TABLES,
    PRODUCTION_INVOCATION_TABLES,
    WORKFLOW_BENCHMARK_EXECUTION_TABLES,
    WORKFLOW_EXPERIMENT_TABLES,
    WORKFLOW_PRODUCTION_REVISION_TABLES,
    WORKFLOW_PRODUCTION_STATE_TABLES,
    WORKFLOW_RUN_EVALUATION_TABLES,
    WORKFLOW_RUN_FEEDBACK_TABLES,
    WORKFLOW_RUN_TABLES,
    WORKFLOW_SPECIFICATION_TABLES,
    ProductionInvocationRepository,
    ProductionInvocationRunRepository,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowBenchmarkExecutionRepository,
    SQLiteWorkflowExperimentRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunEvaluationRepository,
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    SqlProductionInvocationRepository,
    SqlProductionInvocationRunRepository,
    SqlWorkflowBenchmarkExecutionRepository,
    SqlWorkflowExperimentRepository,
    SqlWorkflowProductionRevisionRepository,
    SqlWorkflowProductionStateRepository,
    SqlWorkflowRepository,
    SqlWorkflowRunEvaluationRepository,
    SqlWorkflowRunFeedbackRepository,
    SqlWorkflowRunRepository,
    WorkflowBenchmarkExecutionRepository,
    WorkflowExperimentRepository,
    WorkflowProductionRevisionRepository,
    WorkflowProductionStateRepository,
    WorkflowRepository,
    WorkflowRunEvaluationRepository,
    WorkflowRunFeedbackRepository,
    WorkflowRunRepository,
)

SCHEMA_TABLES: Final[tuple[Table, ...]] = (
    *WORKFLOW_SPECIFICATION_TABLES,
    *WORKFLOW_PRODUCTION_STATE_TABLES,
    *WORKFLOW_PRODUCTION_REVISION_TABLES,
    *WORKFLOW_RUN_TABLES,
    *WORKFLOW_RUN_EVALUATION_TABLES,
    *WORKFLOW_RUN_FEEDBACK_TABLES,
    *WORKFLOW_EXPERIMENT_TABLES,
    *WORKFLOW_BENCHMARK_EXECUTION_TABLES,
    *PRODUCTION_INVOCATION_TABLES,
    *PRODUCTION_INVOCATION_RUN_TABLES,
    *TOOL_TABLES,
    *BENCHMARK_TABLES,
    *GOAL_TABLES,
    *JUDGE_ROTATION_TABLES,
    *MODEL_TABLES,
    *MODEL_PORTFOLIO_TABLES,
    *PROVIDER_MODEL_OBSERVATION_TABLES,
    *CONTENT_TABLES,
)
"""Every table of the schema, in the order `initialize` creates them.

Production invocations come before their results, whose foreign key needs
them.
"""


class Repositories:
    """Every repository of one database, each opened the first time it is used.

    An SQLite database is served by the SQLite repositories, which keep the
    in-place migrations of databases from before 1.1. A PostgreSQL database
    is served by the shared repositories over one `PostgresDatabase`.
    """

    def __init__(
        self,
        location: DatabaseLocation,
        database: Database,
    ) -> None:
        self._location = location
        self._database = database

    @property
    def location(
        self,
    ) -> DatabaseLocation:
        """Return where the database is."""

        return self._location

    @property
    def database(
        self,
    ) -> Database:
        """Return the database the repositories keep their tables in."""

        return self._database

    @property
    def _sqlite_path(
        self,
    ) -> Path | None:
        """Return the SQLite file, or None for PostgreSQL."""

        return self._location.path if isinstance(self._location, SQLiteLocation) else None

    @cached_property
    def workflows(
        self,
    ) -> WorkflowRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowRepository(path)
            if path is not None
            else SqlWorkflowRepository(self._database)
        )

    @cached_property
    def production_states(
        self,
    ) -> WorkflowProductionStateRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowProductionStateRepository(path)
            if path is not None
            else SqlWorkflowProductionStateRepository(self._database)
        )

    @cached_property
    def production_revisions(
        self,
    ) -> WorkflowProductionRevisionRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowProductionRevisionRepository(path)
            if path is not None
            else SqlWorkflowProductionRevisionRepository(self._database)
        )

    @cached_property
    def runs(
        self,
    ) -> WorkflowRunRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowRunRepository(path)
            if path is not None
            else SqlWorkflowRunRepository(self._database)
        )

    @cached_property
    def run_evaluations(
        self,
    ) -> WorkflowRunEvaluationRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowRunEvaluationRepository(path)
            if path is not None
            else SqlWorkflowRunEvaluationRepository(self._database)
        )

    @cached_property
    def feedback(
        self,
    ) -> WorkflowRunFeedbackRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowRunFeedbackRepository(path)
            if path is not None
            else SqlWorkflowRunFeedbackRepository(self._database)
        )

    @cached_property
    def experiments(
        self,
    ) -> WorkflowExperimentRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowExperimentRepository(path)
            if path is not None
            else SqlWorkflowExperimentRepository(self._database)
        )

    @cached_property
    def benchmark_executions(
        self,
    ) -> WorkflowBenchmarkExecutionRepository:
        path = self._sqlite_path

        return (
            SQLiteWorkflowBenchmarkExecutionRepository(path)
            if path is not None
            else SqlWorkflowBenchmarkExecutionRepository(self._database)
        )

    @cached_property
    def invocations(
        self,
    ) -> ProductionInvocationRepository:
        path = self._sqlite_path

        return (
            SQLiteProductionInvocationRepository(path)
            if path is not None
            else SqlProductionInvocationRepository(self._database)
        )

    @cached_property
    def invocation_runs(
        self,
    ) -> ProductionInvocationRunRepository:
        path = self._sqlite_path

        return (
            SQLiteProductionInvocationRunRepository(path)
            if path is not None
            else SqlProductionInvocationRunRepository(self._database)
        )

    @cached_property
    def tools(
        self,
    ) -> ToolRepository:
        path = self._sqlite_path

        return SQLiteToolRepository(path) if path is not None else SqlToolRepository(self._database)

    @cached_property
    def benchmarks(
        self,
    ) -> BenchmarkRepository:
        path = self._sqlite_path

        return (
            SQLiteBenchmarkRepository(path)
            if path is not None
            else SqlBenchmarkRepository(self._database)
        )

    @cached_property
    def goals(
        self,
    ) -> GoalRepository:
        path = self._sqlite_path

        return SQLiteGoalRepository(path) if path is not None else SqlGoalRepository(self._database)

    @cached_property
    def judges(
        self,
    ) -> JudgeRotationRepository:
        path = self._sqlite_path

        return (
            SQLiteJudgeRotationRepository(path)
            if path is not None
            else SqlJudgeRotationRepository(self._database)
        )

    @cached_property
    def models(
        self,
    ) -> ModelRepository:
        path = self._sqlite_path

        return (
            SQLiteModelRepository(path) if path is not None else SqlModelRepository(self._database)
        )

    @cached_property
    def portfolio(
        self,
    ) -> ModelPortfolioRepository:
        path = self._sqlite_path

        return (
            SQLiteModelPortfolioRepository(path)
            if path is not None
            else SqlModelPortfolioRepository(self._database)
        )

    @cached_property
    def provider_observations(
        self,
    ) -> ProviderModelObservationRepository:
        path = self._sqlite_path

        return (
            SQLiteProviderModelObservationRepository(path)
            if path is not None
            else SqlProviderModelObservationRepository(self._database)
        )

    @cached_property
    def content(
        self,
    ) -> ContentStore:
        path = self._sqlite_path

        return SQLiteContentStore(path) if path is not None else SqlContentStore(self._database)


_POSTGRES_DATABASES: dict[PostgresLocation, PostgresDatabase] = {}


def postgres_database(
    location: PostgresLocation,
) -> PostgresDatabase:
    """Return this process's one database for a PostgreSQL location.

    Every repository over the same URL shares its connection, which is opened
    when it is first used.

    Raises:
        DatabaseUnavailableError: The `postgres` extra is not installed.
    """

    database = _POSTGRES_DATABASES.get(location)

    if database is None:
        database = PostgresDatabase(location)
        _POSTGRES_DATABASES[location] = database

    return database


def close_postgres_databases() -> None:
    """Close every PostgreSQL connection this process opened."""

    for database in _POSTGRES_DATABASES.values():
        database.close()

    _POSTGRES_DATABASES.clear()


def open_repositories(
    location: DatabaseLocation | str | Path,
) -> Repositories:
    """Return every repository of the database one location names.

    Nothing is opened until a repository is first used.

    Raises:
        DatabaseUnavailableError: It is a PostgreSQL database, and the
            `postgres` extra is not installed.
    """

    resolved = (
        location
        if isinstance(location, SQLiteLocation | PostgresLocation)
        else parse_database_location(location)
    )

    if isinstance(resolved, PostgresLocation):
        return Repositories(resolved, postgres_database(resolved))

    return Repositories(resolved, SQLiteDatabase(resolved.path))


__all__ = [
    "SCHEMA_TABLES",
    "Repositories",
    "close_postgres_databases",
    "open_repositories",
    "postgres_database",
]
