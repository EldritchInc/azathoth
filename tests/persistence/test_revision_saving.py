"""Tests of saving revisions with an author, on the revision they build on (ADR 0122).

Each test runs on the in-memory repositories, on SQLite, and on PostgreSQL
when one is named.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from azathoth.evaluation import (
    BENCHMARK_TABLES,
    BenchmarkRepository,
    InMemoryBenchmarkRepository,
    SqlBenchmarkRepository,
)
from azathoth.persistence import Database, SQLiteDatabase
from azathoth.providers import (
    MODEL_PORTFOLIO_PROVENANCE_TABLES,
    MODEL_PORTFOLIO_TABLES,
    InMemoryModelPortfolioRepository,
    ModelPortfolioEntry,
    ModelPortfolioRepository,
    SqlModelPortfolioRepository,
)
from azathoth.revisions import (
    Author,
    BaseRevisionError,
    Lineage,
    LineageRecord,
    RevisionKind,
    revision_digest,
    tables_with_lineage,
)
from azathoth.tools import (
    TOOL_TABLES,
    InMemoryToolRepository,
    SqlToolRepository,
    ToolDocument,
    ToolRepository,
)
from azathoth.workflows import (
    WORKFLOW_SPECIFICATION_TABLES,
    InMemoryWorkflowRepository,
    SqlWorkflowRepository,
    WorkflowRepository,
)
from tests.cli.test_benchmark_import import BENCHMARK_ID, create_dataset
from tests.cli.test_tool_import import TOOL_ID, create_document
from tests.evaluation.test_benchmark_revision_repository import create_changed_dataset
from tests.workflows.test_repository import WORKFLOW_ID, create_workflow
from tests.workflows.test_workflow_revision_repository import create_changed_workflow

KINDS = ("memory", "sqlite", "postgres")

ERIS = Author(
    name="Eris Discordia",
    email="eris@example.com",
)

OREN = Author(
    name="oren",
)

WORKFLOW = Lineage(
    kind=RevisionKind.WORKFLOW,
    id=WORKFLOW_ID,
)

TOOL = Lineage(
    kind=RevisionKind.TOOL,
    id=TOOL_ID,
    version="1.0.0",
)

BENCHMARK = Lineage(
    kind=RevisionKind.BENCHMARK,
    id=BENCHMARK_ID,
)

ENTRY = ModelPortfolioEntry(
    provider="openrouter",
    model="example/frontier",
)


@pytest.fixture(params=KINDS)
def open_database(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[Callable[[], Database] | None]:
    """Return how to reach a fresh database of each kind in turn, or None for memory."""

    if request.param == "memory":
        yield None
    elif request.param == "sqlite":
        database = SQLiteDatabase(tmp_path / "azathoth.db")

        yield lambda: database
    else:
        postgres: Database = request.getfixturevalue("postgres_database")

        yield lambda: postgres


@pytest.fixture
def workflows(
    open_database: Callable[[], Database] | None,
) -> WorkflowRepository:
    if open_database is None:
        return InMemoryWorkflowRepository()

    database = open_database()
    database.initialize(tables_with_lineage(WORKFLOW_SPECIFICATION_TABLES))

    return SqlWorkflowRepository(database)


@pytest.fixture
def tools(
    open_database: Callable[[], Database] | None,
) -> ToolRepository:
    if open_database is None:
        return InMemoryToolRepository()

    database = open_database()
    database.initialize(tables_with_lineage(TOOL_TABLES))

    return SqlToolRepository(database)


@pytest.fixture
def benchmarks(
    open_database: Callable[[], Database] | None,
) -> BenchmarkRepository:
    if open_database is None:
        return InMemoryBenchmarkRepository()

    database = open_database()
    database.initialize(tables_with_lineage(BENCHMARK_TABLES))

    return SqlBenchmarkRepository(database)


@pytest.fixture
def portfolio(
    open_database: Callable[[], Database] | None,
) -> ModelPortfolioRepository:
    if open_database is None:
        return InMemoryModelPortfolioRepository()

    database = open_database()
    database.initialize((*MODEL_PORTFOLIO_TABLES, *MODEL_PORTFOLIO_PROVENANCE_TABLES))

    return SqlModelPortfolioRepository(database)


def changed_tool_document() -> ToolDocument:
    document = create_document()

    return document.model_copy(
        update={
            "definition": document.definition.model_copy(
                update={
                    "description": "Changed tool.",
                },
            ),
        },
    )


def other_tool_document() -> ToolDocument:
    document = create_document()

    return document.model_copy(
        update={
            "definition": document.definition.model_copy(
                update={
                    "description": "Another tool.",
                },
            ),
        },
    )


# Workflows


def test_a_saved_workflow_revision_is_new_and_records_its_author(
    workflows: WorkflowRepository,
) -> None:
    saved = workflows.save_revision(create_workflow(), author=ERIS)

    assert saved.created
    assert saved.revision == workflows.latest_revision(WORKFLOW_ID)
    assert saved.lineage == LineageRecord(
        lineage=WORKFLOW,
        number=1,
        revision_digest=revision_digest(
            WORKFLOW,
            content_digest=saved.revision.content_digest,
            parent_digest=None,
        ),
        parent_digest=None,
        author=ERIS,
    )
    assert workflows.lineage(WORKFLOW_ID) == (saved.lineage,)


def test_saving_a_workflow_without_an_author_records_none(
    workflows: WorkflowRepository,
) -> None:
    workflows.save(create_workflow())

    (record,) = workflows.lineage(WORKFLOW_ID)

    assert record.author is None


def test_a_workflow_identical_to_the_latest_appends_nothing(
    workflows: WorkflowRepository,
) -> None:
    first = workflows.save_revision(create_workflow(), author=ERIS)
    again = workflows.save_revision(create_workflow(), author=OREN)

    assert not again.created
    assert again.revision == first.revision
    assert again.lineage == first.lineage
    assert workflows.lineage(WORKFLOW_ID) == (first.lineage,)


def test_a_workflow_reverted_to_an_earlier_revision_is_appended(
    workflows: WorkflowRepository,
) -> None:
    workflows.save(create_workflow())
    second = workflows.save_revision(create_changed_workflow())
    reverted = workflows.save_revision(create_workflow())

    assert reverted.created
    assert reverted.revision.number == 3
    assert reverted.lineage.parent_digest == second.lineage.revision_digest


def test_a_workflow_built_on_an_earlier_revision_forks(
    workflows: WorkflowRepository,
) -> None:
    first = workflows.save_revision(create_workflow())
    workflows.save(create_changed_workflow())

    fork = workflows.save_revision(
        create_workflow(name="Forked workflow"),
        author=OREN,
        based_on=first.lineage.revision_digest,
    )

    assert fork.created
    assert fork.revision.number == 3
    assert fork.lineage.parent_digest == first.lineage.revision_digest
    assert fork.lineage.author == OREN
    assert workflows.get(WORKFLOW_ID) == fork.revision.specification


def test_a_workflow_identical_to_the_revision_it_builds_on_appends_nothing(
    workflows: WorkflowRepository,
) -> None:
    first = workflows.save_revision(create_workflow())
    workflows.save(create_changed_workflow())

    again = workflows.save_revision(create_workflow(), based_on=first.lineage.revision_digest)

    assert not again.created
    assert again.revision == first.revision
    assert len(workflows.lineage(WORKFLOW_ID)) == 2


def test_a_workflow_built_on_an_unknown_revision_is_refused(
    workflows: WorkflowRepository,
) -> None:
    workflows.save(create_workflow())

    with pytest.raises(BaseRevisionError) as caught:
        workflows.save(create_changed_workflow(), based_on="f" * 64)

    assert str(caught.value) == f"Revision {'f' * 64} is not a revision of workflow {WORKFLOW_ID}."
    assert len(workflows.revisions(WORKFLOW_ID)) == 1


def test_a_workflows_first_revision_cannot_build_on_anything(
    workflows: WorkflowRepository,
) -> None:
    with pytest.raises(BaseRevisionError):
        workflows.save(create_workflow(), based_on="f" * 64)

    assert workflows.revisions(WORKFLOW_ID) == ()


def test_save_returns_the_revision_save_revision_does(
    workflows: WorkflowRepository,
) -> None:
    saved = workflows.save(create_workflow(), author=ERIS)

    assert saved == workflows.save_revision(create_workflow()).revision
    assert workflows.lineage(WORKFLOW_ID)[0].author == ERIS


# Tools


def test_a_saved_tool_revision_records_its_author(
    tools: ToolRepository,
) -> None:
    saved = tools.save_document_revision(create_document(), author=ERIS)

    assert saved.created
    assert saved.lineage.lineage == TOOL
    assert saved.lineage.author == ERIS
    assert tools.document_lineage(TOOL_ID, "1.0.0") == (saved.lineage,)


def test_a_tool_identical_to_the_latest_appends_nothing(
    tools: ToolRepository,
) -> None:
    first = tools.save_document_revision(create_document())
    again = tools.save_document_revision(create_document())

    assert not again.created
    assert again.revision == first.revision
    assert len(tools.document_revisions(TOOL_ID)) == 1


def test_a_tool_built_on_an_earlier_revision_forks_and_becomes_current(
    tools: ToolRepository,
) -> None:
    first = tools.save_document_revision(create_document())
    tools.save_document(changed_tool_document())

    fork = tools.save_document_revision(
        other_tool_document(),
        based_on=first.lineage.revision_digest,
    )

    assert fork.revision.number == 3
    assert fork.lineage.parent_digest == first.lineage.revision_digest
    assert tools.get_definition(TOOL_ID, "1.0.0") == other_tool_document().definition


def test_a_tool_identical_to_the_revision_it_builds_on_changes_no_artifact(
    tools: ToolRepository,
) -> None:
    first = tools.save_document_revision(create_document())
    tools.save_document(changed_tool_document())

    again = tools.save_document_revision(create_document(), based_on=first.lineage.revision_digest)

    assert not again.created
    assert again.revision == first.revision
    assert tools.get_definition(TOOL_ID, "1.0.0") == changed_tool_document().definition


def test_a_tool_built_on_another_versions_revision_is_refused(
    tools: ToolRepository,
) -> None:
    first = tools.save_document_revision(create_document())
    other_version = create_document().model_copy(
        update={
            "definition": create_document().definition.model_copy(update={"version": "9.0.0"}),
            "implementations": (),
        },
    )

    with pytest.raises(BaseRevisionError) as caught:
        tools.save_document(other_version, based_on=first.lineage.revision_digest)

    assert str(caught.value) == (
        f"Revision {first.lineage.revision_digest} is not a revision of tool {TOOL_ID}@9.0.0."
    )


# Benchmarks


def test_a_saved_benchmark_revision_records_its_author(
    benchmarks: BenchmarkRepository,
) -> None:
    saved = benchmarks.save_revision(create_dataset(), author=ERIS)

    assert saved.created
    assert saved.lineage.lineage == BENCHMARK
    assert saved.lineage.author == ERIS
    assert benchmarks.lineage(BENCHMARK_ID) == (saved.lineage,)


def test_a_benchmark_identical_to_the_latest_appends_nothing(
    benchmarks: BenchmarkRepository,
) -> None:
    first = benchmarks.save_revision(create_dataset())
    again = benchmarks.save_revision(create_dataset())

    assert not again.created
    assert again.revision == first.revision


def test_a_benchmark_built_on_an_earlier_revision_forks(
    benchmarks: BenchmarkRepository,
) -> None:
    first = benchmarks.save_revision(create_dataset())
    benchmarks.save(create_changed_dataset())

    fork = benchmarks.save_revision(
        create_changed_dataset().model_copy(update={"description": "Forked."}),
        based_on=first.lineage.revision_digest,
    )

    assert fork.revision.number == 3
    assert fork.lineage.parent_digest == first.lineage.revision_digest


def test_a_benchmark_identical_to_the_revision_it_builds_on_appends_nothing(
    benchmarks: BenchmarkRepository,
) -> None:
    first = benchmarks.save_revision(create_dataset())
    benchmarks.save(create_changed_dataset())

    again = benchmarks.save_revision(create_dataset(), based_on=first.lineage.revision_digest)

    assert not again.created
    assert again.revision == first.revision


def test_a_benchmark_built_on_an_unknown_revision_is_refused(
    benchmarks: BenchmarkRepository,
) -> None:
    benchmarks.save(create_dataset())

    with pytest.raises(BaseRevisionError, match="is not a revision of benchmark"):
        benchmarks.save(create_changed_dataset(), based_on="0" * 64)


# The portfolio


def test_a_portfolio_entry_records_who_added_it(
    portfolio: ModelPortfolioRepository,
) -> None:
    portfolio.save(ENTRY, author=ERIS)

    provenance = portfolio.provenance(ENTRY.identifier)

    assert provenance is not None
    assert provenance.author == ERIS
    assert provenance.added_at is not None


def test_a_portfolio_entry_added_without_an_author_records_none(
    portfolio: ModelPortfolioRepository,
) -> None:
    portfolio.save(ENTRY)

    provenance = portfolio.provenance(ENTRY.identifier)

    assert provenance is not None
    assert provenance.author is None


def test_a_removed_portfolio_entry_has_no_provenance(
    portfolio: ModelPortfolioRepository,
) -> None:
    portfolio.save(ENTRY, author=ERIS)
    portfolio.delete(ENTRY.identifier)

    assert portfolio.provenance(ENTRY.identifier) is None
