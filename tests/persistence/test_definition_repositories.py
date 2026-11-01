"""Contract tests of the definition repositories, on SQLite and PostgreSQL (ADR 0102).

Workflows, production states and revisions, tools, benchmarks, goals and
the judge rotation behave the same in either database: revisions are
numbered from 1 per artifact, read back exactly and in order, duplicates are
refused, and, on PostgreSQL, concurrent writers never take the same number.
"""

import threading
from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

import pytest

from azathoth.evaluation import (
    BENCHMARK_TABLES,
    JUDGE_ROTATION_TABLES,
    BenchmarkRepository,
    JudgeEntry,
    JudgeRotationRepository,
    SqlBenchmarkRepository,
    SqlJudgeRotationRepository,
)
from azathoth.goals import GOAL_TABLES, GoalRepository, SqlGoalRepository
from azathoth.persistence import Database, PostgresDatabase, Table
from azathoth.revisions import content_digest
from azathoth.tools import (
    TOOL_TABLES,
    SqlToolRepository,
    ToolRepository,
)
from azathoth.workflows import (
    WORKFLOW_PRODUCTION_REVISION_TABLES,
    WORKFLOW_PRODUCTION_STATE_TABLES,
    WORKFLOW_SPECIFICATION_TABLES,
    SqlWorkflowProductionRevisionRepository,
    SqlWorkflowProductionStateRepository,
    SqlWorkflowRepository,
    WorkflowProductionRevisionRepository,
    WorkflowProductionStateRepository,
    WorkflowRepository,
)
from tests.cli.test_benchmark_import import BENCHMARK_ID, create_dataset
from tests.cli.test_tool_import import (
    TOOL_ID,
    create_changed_document,
    create_definition,
    create_document,
    create_implementation,
    create_test_case,
)
from tests.evaluation.test_benchmark_revision_repository import create_changed_dataset
from tests.goals.test_repository import FIRST_GOAL_ID, SECOND_GOAL_ID, create_goal
from tests.tools.test_tool_revision_repository import create_second_version_document
from tests.workflows.test_production_repository import (
    FIRST_WORKFLOW_ID,
    SECOND_WORKFLOW_ID,
    create_state,
)
from tests.workflows.test_production_revision_repository import (
    FIRST_REVISION_ID,
    create_revision,
)
from tests.workflows.test_repository import (
    SECOND_WORKFLOW_ID as SECOND_SPECIFICATION_ID,
)
from tests.workflows.test_repository import WORKFLOW_ID, create_workflow
from tests.workflows.test_workflow_revision_repository import create_changed_workflow

Repository = TypeVar("Repository")

ALPHA = JudgeEntry(provider="openrouter", model="alpha")
BETA = JudgeEntry(provider="openrouter", model="beta")
GAMMA = JudgeEntry(provider="openrouter", model="gamma")


def initialized(
    database: Database,
    tables: tuple[Table, ...],
    factory: Callable[[Database], Repository],
) -> Repository:
    """Initialize a database with a repository's tables, then open the repository."""

    database.initialize(tables)

    return factory(database)


def concurrently(
    postgres_url: str,
    tables: tuple[Table, ...],
    write: Callable[[Database], None],
    *,
    writers: int = 4,
) -> None:
    """Run one write from several processes' worth of connections at once."""

    databases = [PostgresDatabase(postgres_url) for _ in range(writers)]
    failures: list[BaseException] = []

    databases[0].initialize(tables)

    def run(
        database: Database,
    ) -> None:
        try:
            write(database)
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=run, args=(database,)) for database in databases]

    try:
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
    finally:
        for database in databases:
            database.close()

    assert failures == []


# Workflow specifications


def workflows(
    database: Database,
) -> WorkflowRepository:
    return initialized(database, WORKFLOW_SPECIFICATION_TABLES, SqlWorkflowRepository)


def test_workflow_revisions_are_numbered_and_read_back(
    database: Database,
) -> None:
    repository = workflows(database)

    first = repository.save(create_workflow())
    second = repository.save(create_changed_workflow())

    assert (first.number, second.number) == (1, 2)
    assert second.content_digest == content_digest(create_changed_workflow())
    assert repository.get(WORKFLOW_ID) == create_changed_workflow()
    assert repository.latest_revision(WORKFLOW_ID) == second
    assert repository.revision(WORKFLOW_ID, 1) == first
    assert repository.revision(WORKFLOW_ID, 3) is None
    assert repository.revisions(WORKFLOW_ID) == (first, second)
    assert repository.get(UUID(int=0)) is None


def test_workflows_list_their_latest_specification_in_first_import_order(
    database: Database,
) -> None:
    repository = workflows(database)

    repository.save(create_workflow())
    other = create_workflow().model_copy(
        update={
            "metadata": create_workflow().metadata.model_copy(
                update={"id": SECOND_SPECIFICATION_ID, "name": "Second"}
            )
        }
    )
    repository.save(other)
    repository.save(create_changed_workflow())

    assert repository.specifications() == (create_changed_workflow(), other)


def test_concurrent_imports_never_take_the_same_workflow_revision(
    postgres_url: str,
) -> None:
    def write(
        database: Database,
    ) -> None:
        repository = SqlWorkflowRepository(database)

        for _ in range(5):
            repository.save(create_workflow())

    concurrently(postgres_url, WORKFLOW_SPECIFICATION_TABLES, write)

    database = PostgresDatabase(postgres_url)

    try:
        numbers = [
            revision.number for revision in SqlWorkflowRepository(database).revisions(WORKFLOW_ID)
        ]
    finally:
        database.close()

    assert numbers == list(range(1, 21))


# Production states


def states(
    database: Database,
) -> WorkflowProductionStateRepository:
    return initialized(
        database,
        WORKFLOW_PRODUCTION_STATE_TABLES,
        SqlWorkflowProductionStateRepository,
    )


def test_a_production_state_is_replaced_in_place(
    database: Database,
) -> None:
    repository = states(database)

    repository.set(create_state(workflow_id=FIRST_WORKFLOW_ID, model="first-model"))
    repository.set(create_state(workflow_id=SECOND_WORKFLOW_ID))
    repository.set(create_state(workflow_id=FIRST_WORKFLOW_ID, model="second-model"))

    assert repository.get(FIRST_WORKFLOW_ID) == create_state(
        workflow_id=FIRST_WORKFLOW_ID, model="second-model"
    )
    assert repository.get(UUID(int=0)) is None
    assert repository.states() == (
        create_state(workflow_id=FIRST_WORKFLOW_ID, model="second-model"),
        create_state(workflow_id=SECOND_WORKFLOW_ID),
    )


# Production revisions


def production_revisions(
    database: Database,
) -> WorkflowProductionRevisionRepository:
    return initialized(
        database,
        WORKFLOW_PRODUCTION_REVISION_TABLES,
        SqlWorkflowProductionRevisionRepository,
    )


def test_production_revisions_keep_history_in_order(
    database: Database,
) -> None:
    repository = production_revisions(database)

    first = create_revision()
    second = create_revision(revision_id=UUID(int=2), workflow_id=SECOND_WORKFLOW_ID)
    third = create_revision(revision_id=UUID(int=3), model="later-model")

    for revision in (first, second, third):
        repository.save(revision)

    assert repository.get(FIRST_REVISION_ID) == first
    assert repository.get(UUID(int=9)) is None
    assert repository.revisions() == (first, second, third)
    assert repository.revisions_for_workflow(first.workflow_id) == (first, third)


def test_a_duplicate_production_revision_is_refused(
    database: Database,
) -> None:
    repository = production_revisions(database)
    repository.save(create_revision())

    with pytest.raises(ValueError, match=f"production revision {FIRST_REVISION_ID} already"):
        repository.save(create_revision(model="other"))


# Tools


def tools(
    database: Database,
) -> ToolRepository:
    return initialized(database, TOOL_TABLES, SqlToolRepository)


def test_tool_documents_are_revisioned_per_version(
    database: Database,
) -> None:
    repository = tools(database)

    first = repository.save_document(create_document())
    second = repository.save_document(create_changed_document())
    other = repository.save_document(create_second_version_document())

    assert (first.number, second.number, other.number) == (1, 2, 1)
    assert repository.latest_document_revision(TOOL_ID, "1.0.0") == second
    assert repository.latest_document_revision(TOOL_ID, "2.0.0") == other
    assert repository.document_revision(TOOL_ID, "1.0.0", 1) == first
    assert repository.document_revision(TOOL_ID, "1.0.0", 9) is None
    assert repository.document_revisions(TOOL_ID) == (first, second, other)


def test_a_tool_document_sets_the_current_artifacts(
    database: Database,
) -> None:
    repository = tools(database)

    repository.save_document(create_document())
    repository.save_document(create_changed_document())

    changed = create_changed_document()

    assert repository.get_definition(TOOL_ID, "1.0.0") == changed.definition
    assert repository.definitions() == (changed.definition,)
    assert repository.implementations() == changed.implementations
    assert repository.test_cases() == changed.test_cases

    for implementation in changed.implementations:
        assert repository.get_implementation(implementation.id) == implementation


def test_artifacts_saved_one_at_a_time_are_kept_and_refused_twice(
    database: Database,
) -> None:
    repository = tools(database)

    repository.save_definition(create_definition())
    repository.save_implementation(create_implementation())
    repository.save_test_case(create_test_case())

    assert repository.get_definition(TOOL_ID, "1.0.0") == create_definition()
    assert repository.get_definition(TOOL_ID, "9.9.9") is None
    assert repository.get_implementation(create_implementation().id) == create_implementation()
    assert repository.get_test_case(create_test_case().id) == create_test_case()
    assert repository.get_test_case(UUID(int=0)) is None

    with pytest.raises(ValueError, match="already exists"):
        repository.save_definition(create_definition())

    with pytest.raises(ValueError, match="Tool implementation .* already exists"):
        repository.save_implementation(create_implementation())

    with pytest.raises(ValueError, match="Tool test case .* already exists"):
        repository.save_test_case(create_test_case())


def test_a_version_saved_artifact_by_artifact_becomes_revision_1_when_a_document_follows(
    database: Database,
) -> None:
    repository = tools(database)

    repository.save_definition(create_definition())
    repository.save_implementation(create_implementation())
    repository.save_test_case(create_test_case())

    revision = repository.save_document(create_changed_document())

    revisions = repository.document_revisions(TOOL_ID)

    assert revision.number == 2
    assert [entry.number for entry in revisions] == [1, 2]
    assert revisions[0].imported_at is None


def test_concurrent_imports_never_take_the_same_tool_revision(
    postgres_url: str,
) -> None:
    def write(
        database: Database,
    ) -> None:
        repository = SqlToolRepository(database)

        for document in (create_document(), create_changed_document()) * 2:
            repository.save_document(document)

    concurrently(postgres_url, TOOL_TABLES, write)

    database = PostgresDatabase(postgres_url)

    try:
        numbers = [
            revision.number for revision in SqlToolRepository(database).document_revisions(TOOL_ID)
        ]
    finally:
        database.close()

    assert numbers == list(range(1, 17))


# Benchmarks


def benchmarks(
    database: Database,
) -> BenchmarkRepository:
    return initialized(database, BENCHMARK_TABLES, SqlBenchmarkRepository)


def test_benchmark_revisions_are_numbered_and_read_back(
    database: Database,
) -> None:
    repository = benchmarks(database)

    first = repository.save(create_dataset())
    second = repository.save(create_changed_dataset())

    assert (first.number, second.number) == (1, 2)
    assert repository.get(BENCHMARK_ID) == create_changed_dataset()
    assert repository.latest_revision(BENCHMARK_ID) == second
    assert repository.revision(BENCHMARK_ID, 1) == first
    assert repository.revision(BENCHMARK_ID, 3) is None
    assert repository.revisions(BENCHMARK_ID) == (first, second)
    assert repository.datasets() == (create_changed_dataset(),)
    assert repository.get(UUID(int=0)) is None


def test_concurrent_imports_never_take_the_same_benchmark_revision(
    postgres_url: str,
) -> None:
    def write(
        database: Database,
    ) -> None:
        repository = SqlBenchmarkRepository(database)

        for _ in range(5):
            repository.save(create_dataset())

    concurrently(postgres_url, BENCHMARK_TABLES, write)

    database = PostgresDatabase(postgres_url)

    try:
        numbers = [
            revision.number for revision in SqlBenchmarkRepository(database).revisions(BENCHMARK_ID)
        ]
    finally:
        database.close()

    assert numbers == list(range(1, 21))


# Goals


def goals(
    database: Database,
) -> GoalRepository:
    return initialized(database, GOAL_TABLES, SqlGoalRepository)


def test_goals_read_back_in_order_and_are_refused_twice(
    database: Database,
) -> None:
    repository = goals(database)

    second = create_goal(goal_id=SECOND_GOAL_ID, name="Answer briefly")
    first = create_goal()

    repository.save(second)
    repository.save(first)

    assert repository.get(FIRST_GOAL_ID) == first
    assert repository.get(UUID(int=0)) is None
    assert repository.goals() == (second, first)

    with pytest.raises(ValueError, match=f"Goal {FIRST_GOAL_ID} already exists."):
        repository.save(first)


# The judge rotation


def judges(
    database: Database,
) -> JudgeRotationRepository:
    return initialized(database, JUDGE_ROTATION_TABLES, SqlJudgeRotationRepository)


def test_the_judge_rotation_keeps_the_order_judges_were_added(
    database: Database,
) -> None:
    repository = judges(database)

    for entry in (BETA, ALPHA, GAMMA):
        repository.add(entry)

    repository.remove(ALPHA.identifier)

    assert repository.rotation().entries == (BETA, GAMMA)
    assert repository.get(BETA.identifier) == BETA
    assert repository.get(ALPHA.identifier) is None


def test_the_judge_rotation_refuses_a_duplicate_and_an_unknown_removal(
    database: Database,
) -> None:
    repository = judges(database)
    repository.add(ALPHA)

    with pytest.raises(ValueError, match="is already in the rotation"):
        repository.add(ALPHA)

    with pytest.raises(ValueError, match="is not in the rotation"):
        repository.remove(BETA.identifier)

    assert repository.rotation().entries == (ALPHA,)
