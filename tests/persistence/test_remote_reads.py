"""Tests that what a remote serves is read in read-only transactions (ADR 0135).

A remote answers requests together, so its reads must not take the write
lock: each repository it serves reads in a read-only transaction, and
writes only where it writes.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager
from functools import partial
from uuid import UUID

import pytest

from azathoth.evaluation import SqlBenchmarkRepository
from azathoth.inputs import SqlContentStore
from azathoth.persistence import (
    Database,
    InitializationOutcome,
    Session,
    Table,
)
from azathoth.persistence.dialect import Dialect
from azathoth.persistence.location import DatabaseLocation
from azathoth.persistence.repositories import SCHEMA_TABLES
from azathoth.providers import ModelPortfolioEntry, SqlModelPortfolioRepository
from azathoth.remote import (
    HeadsRequest,
    MissingRequest,
    PullRequest,
    SqlRemoteTokenRepository,
    TokenAuthenticator,
)
from azathoth.remote.closure import lineage_records
from azathoth.remote.inspection import heads, portfolio_records
from azathoth.remote.pulling import pull
from azathoth.sensitivity import PRIVATE_DATA_POLICY
from azathoth.tools import SqlToolRepository
from azathoth.workflows import (
    SqlWorkflowProductionStateRepository,
    SqlWorkflowRepository,
    WorkflowProductionState,
)
from tests.remote.test_closure import (
    BENCHMARK,
    BENCHMARK_ID,
    CHILD,
    COUNT_ID,
    PARENT,
    PARENT_ID,
    Instance,
)
from tests.remote.test_receiving import (
    CHART,
    CHART_BYTES,
    bundle,
    charts,
    local_with_history,
    received_by,
)

READ = "read"

WRITE = "write"

PORTFOLIO_ENTRY = ModelPortfolioEntry(
    provider="bedrock",
    model="example/private",
    data_policy=PRIVATE_DATA_POLICY,
)


class RecordingDatabase:
    """A database that notes whether each transaction it runs only reads."""

    def __init__(
        self,
        inner: Database,
    ) -> None:
        self.inner = inner
        self.kinds: list[str] = []

    @property
    def dialect(
        self,
    ) -> Dialect:
        return self.inner.dialect

    @property
    def location(
        self,
    ) -> DatabaseLocation:
        return self.inner.location

    def transaction(
        self,
        *,
        lock: str | None = None,
        read_only: bool = False,
    ) -> AbstractContextManager[Session]:
        self.kinds.append(READ if read_only else WRITE)

        return self.inner.transaction(lock=lock, read_only=read_only)

    def prepare(
        self,
        tables: Sequence[Table],
    ) -> None:
        self.inner.prepare(tables)

    def initialize(
        self,
        tables: Sequence[Table],
    ) -> InitializationOutcome:
        return self.inner.initialize(tables)

    def close(
        self,
    ) -> None:
        self.inner.close()

    def recorded(
        self,
        work: Callable[[], object],
    ) -> list[str]:
        """Do some work, and return the kind of each transaction it ran."""

        self.kinds.clear()
        work()

        return list(self.kinds)


class Served(Instance):
    """A remote's repositories, each over one recording database."""

    def __init__(
        self,
        database: RecordingDatabase,
    ) -> None:
        self.database = database
        self.workflows = SqlWorkflowRepository(database)
        self.tools = SqlToolRepository(database)
        self.benchmarks = SqlBenchmarkRepository(database)
        self.content = SqlContentStore(database)
        self.production_states = SqlWorkflowProductionStateRepository(database)
        self.portfolio = SqlModelPortfolioRepository(database)
        self.tokens = SqlRemoteTokenRepository(database)


@pytest.fixture
def served(
    database: Database,
) -> Iterator[Served]:
    """Return a remote holding a pushed history, a benchmark, content, a state and an entry."""

    database.initialize(SCHEMA_TABLES)
    remote = Served(RecordingDatabase(database))

    received_by(remote, bundle(local_with_history(), PARENT))
    remote.content.put(CHART_BYTES)
    received_by(remote, bundle(charts(None), BENCHMARK))
    revision = remote.workflows.latest_revision(PARENT_ID)
    assert revision is not None
    remote.production_states.set(
        WorkflowProductionState(
            specification=revision.specification,
            specification_revision=revision.number,
        )
    )
    remote.portfolio.save(PORTFOLIO_ENTRY)

    yield remote


def only_reads(
    served: Served,
    work: Callable[[], object],
) -> None:
    """Assert that some work ran at least one transaction, and only read-only ones."""

    kinds = served.database.recorded(work)

    assert kinds
    assert set(kinds) == {READ}


# What the protocol's routes read


def test_authenticating_a_token_only_reads(
    served: Served,
) -> None:
    secret = served.tokens.create("laptop").secret
    authenticator = TokenAuthenticator(served.tokens)

    only_reads(served, lambda: authenticator.authenticate(f"Bearer {secret}"))


def test_finding_what_a_push_lacks_only_reads(
    served: Served,
) -> None:
    offered = MissingRequest(
        lineages=(PARENT, CHILD, BENCHMARK),
        revisions=(),
        content=(CHART.digest, "e" * 64),
    )

    def missing() -> None:
        for lineage in offered.lineages:
            lineage_records(
                lineage,
                workflows=served.workflows,
                tools=served.tools,
                benchmarks=served.benchmarks,
            )

        for digest in offered.content:
            served.content.contains(digest)

    only_reads(served, missing)


def test_reading_content_only_reads(
    served: Served,
) -> None:
    only_reads(served, lambda: served.content.get(CHART.digest))
    only_reads(served, lambda: served.content.get("e" * 64))


def test_a_pull_only_reads(
    served: Served,
) -> None:
    only_reads(
        served,
        lambda: pull(
            PullRequest(roots=(PARENT, BENCHMARK), include_restricted=True),
            workflows=served.workflows,
            tools=served.tools,
            benchmarks=served.benchmarks,
        ),
    )


def test_heads_only_read(
    served: Served,
) -> None:
    for lineages in ((), (PARENT, CHILD, BENCHMARK)):
        only_reads(
            served,
            partial(
                heads,
                HeadsRequest(lineages=lineages),
                workflows=served.workflows,
                tools=served.tools,
                benchmarks=served.benchmarks,
                production_states=served.production_states,
            ),
        )


def test_the_portfolio_only_reads(
    served: Served,
) -> None:
    only_reads(served, lambda: portfolio_records(served.portfolio))


# Every read of the repositories a remote serves


def reads_of(
    served: Served,
) -> dict[str, Callable[[], object]]:
    """Return every method of the served repositories that only reads, ready to call."""

    unknown = UUID("c1050000-0000-4000-8000-0000000000ff")

    return {
        "workflows.lineage": lambda: served.workflows.lineage(PARENT_ID),
        "workflows.get": lambda: served.workflows.get(PARENT_ID),
        "workflows.specifications": served.workflows.specifications,
        "workflows.latest_revision": lambda: served.workflows.latest_revision(PARENT_ID),
        "workflows.revision": lambda: served.workflows.revision(PARENT_ID, 1),
        "workflows.revisions": lambda: served.workflows.revisions(PARENT_ID),
        "production_states.get": lambda: served.production_states.get(PARENT_ID),
        "production_states.states": served.production_states.states,
        "tools.get_definition": lambda: served.tools.get_definition(COUNT_ID, "1.0.0"),
        "tools.definitions": served.tools.definitions,
        "tools.get_implementation": lambda: served.tools.get_implementation(unknown),
        "tools.implementations": served.tools.implementations,
        "tools.get_test_case": lambda: served.tools.get_test_case(unknown),
        "tools.test_cases": served.tools.test_cases,
        "tools.document_lineage": lambda: served.tools.document_lineage(COUNT_ID, "1.0.0"),
        "tools.latest_document_revision": lambda: served.tools.latest_document_revision(
            COUNT_ID, "1.0.0"
        ),
        "tools.document_revision": lambda: served.tools.document_revision(COUNT_ID, "1.0.0", 1),
        "tools.document_revisions": lambda: served.tools.document_revisions(COUNT_ID),
        "benchmarks.lineage": lambda: served.benchmarks.lineage(BENCHMARK_ID),
        "benchmarks.get": lambda: served.benchmarks.get(BENCHMARK_ID),
        "benchmarks.datasets": served.benchmarks.datasets,
        "benchmarks.latest_revision": lambda: served.benchmarks.latest_revision(BENCHMARK_ID),
        "benchmarks.revision": lambda: served.benchmarks.revision(BENCHMARK_ID, 1),
        "benchmarks.revisions": lambda: served.benchmarks.revisions(BENCHMARK_ID),
        "content.get": lambda: served.content.get(CHART.digest),
        "content.contains": lambda: served.content.contains(CHART.digest),
        "portfolio.get": lambda: served.portfolio.get(PORTFOLIO_ENTRY.identifier),
        "portfolio.entries": served.portfolio.entries,
        "portfolio.policy_declaration": lambda: served.portfolio.policy_declaration(
            PORTFOLIO_ENTRY.identifier
        ),
        "portfolio.provenance": lambda: served.portfolio.provenance(PORTFOLIO_ENTRY.identifier),
        "tokens.tokens": served.tokens.tokens,
        "tokens.find": lambda: served.tokens.find("azr_not-a-token"),
    }


def test_every_read_of_a_served_repository_is_read_only(
    served: Served,
) -> None:
    writing = {
        name: kinds
        for name, read in reads_of(served).items()
        if set(kinds := served.database.recorded(read)) != {READ}
    }

    assert writing == {}


def test_the_reads_find_what_the_remote_holds(
    served: Served,
) -> None:
    reads = reads_of(served)

    assert reads["workflows.revision"]() is not None
    assert reads["tools.document_revision"]() is not None
    assert reads["benchmarks.revision"]() is not None
    assert reads["content.get"]() == CHART_BYTES
    assert reads["production_states.get"]() is not None
    assert reads["portfolio.get"]() == PORTFOLIO_ENTRY


# What still writes


def test_saving_still_writes(
    served: Served,
) -> None:
    pushed_again = bundle(local_with_history(), PARENT)

    assert READ in served.database.recorded(lambda: received_by(served, pushed_again))

    assert WRITE in served.database.recorded(lambda: served.content.put(b"more"))
    assert WRITE in served.database.recorded(lambda: served.tokens.create("desktop"))
    assert WRITE in served.database.recorded(
        lambda: served.portfolio.delete(PORTFOLIO_ENTRY.identifier)
    )


def test_a_token_is_revoked_in_a_writing_transaction(
    served: Served,
) -> None:
    created = served.tokens.create("laptop")
    kinds = served.database.recorded(lambda: served.tokens.revoke(created.token.name))

    assert kinds == [WRITE]
