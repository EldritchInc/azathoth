"""Tests for comparing what this instance holds with what a remote holds (ADR 0125)."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from azathoth.providers import ModelPortfolioEntry
from azathoth.remote import (
    ComponentStatus,
    InMemoryRemotePortfolioSnapshotRepository,
    ModelStatus,
    PortfolioRecord,
    PortfolioResponse,
    ProtocolMismatchError,
    Relation,
    RemoteClient,
    RemoteRefusedError,
    RemoteStatus,
    status_of,
)
from azathoth.revisions import Lineage
from azathoth.workflows import WorkflowProductionState
from tests.remote.test_client import URL, client_of
from tests.remote.test_closure import (
    BENCHMARK,
    CHILD,
    COUNT,
    COUNT_2,
    PARENT,
    PARENT_ID,
    RUN,
    Instance,
    child,
    parent,
)
from tests.remote.test_pulling import with_benchmark
from tests.remote.test_receiving import local_with_history
from tests.remote.test_server import Remote
from tests.remote.test_status import prompting

SYNCED = datetime(2026, 11, 11, 21, 30, tzinfo=UTC)

FRONTIER = ModelPortfolioEntry(provider="openrouter", model="example/frontier")

PRIVATE = ModelPortfolioEntry(provider="bedrock", model="example/private")


def snapshots() -> InMemoryRemotePortfolioSnapshotRepository:
    return InMemoryRemotePortfolioSnapshotRepository(clock=lambda: SYNCED)


def status(
    local: Instance,
    client: RemoteClient,
    *roots: Lineage,
    kept: InMemoryRemotePortfolioSnapshotRepository | None = None,
) -> RemoteStatus:
    return status_of(
        client,
        roots,
        workflows=local.workflows,
        tools=local.tools,
        benchmarks=local.benchmarks,
        production_states=local.production_states,
        portfolio=local.portfolio,
        snapshots=snapshots() if kept is None else kept,
    )


def relations(
    reported: RemoteStatus,
) -> list[tuple[Lineage, Relation | None]]:
    return [(component.lineage, component.relation) for component in reported.components]


def unreachable() -> RemoteClient:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    return RemoteClient(
        URL,
        "azr_token",
        http=httpx.Client(base_url=URL, transport=httpx.MockTransport(refuse)),
    )


# Components


def test_with_nothing_named_every_lineage_either_side_holds_is_reported(
    tmp_path: Path,
) -> None:
    theirs = with_benchmark(Instance(), None)
    theirs.workflows.save(child())
    theirs.workflows.save(parent())

    reported = status(local_with_history(), client_of(Remote(tmp_path, held=theirs)))

    assert reported.reachable
    assert relations(reported) == [
        (CHILD, Relation.IN_SYNC),
        (PARENT, Relation.AHEAD),
        (COUNT, Relation.IN_SYNC),
        (COUNT_2, Relation.IN_SYNC),
        (RUN, Relation.IN_SYNC),
        (BENCHMARK, Relation.REMOTE_ONLY),
    ]


def test_a_component_names_each_sides_latest_revision(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    local = local_with_history()

    (component,) = status(local, client_of(Remote(tmp_path, held=theirs)), PARENT).components

    assert component == ComponentStatus(
        lineage=PARENT,
        relation=Relation.AHEAD,
        local_digest=local.workflows.lineage(PARENT_ID)[-1].revision_digest,
        local_number=2,
        remote_digest=theirs.workflows.lineage(PARENT_ID)[-1].revision_digest,
        remote_number=1,
    )


@pytest.mark.parametrize(
    ("theirs_saves", "expected"),
    [
        (("Counts.", "Counts again.", "Counts once more."), Relation.BEHIND),
        (("Counts.", "Counts differently."), Relation.DIVERGED),
        (("Counts.", "Counts again."), Relation.IN_SYNC),
    ],
    ids=["behind", "diverged", "in-sync"],
)
def test_a_lineage_relates_as_each_side_holds_it(
    tmp_path: Path,
    theirs_saves: tuple[str, ...],
    expected: Relation,
) -> None:
    theirs = Instance()

    for description in theirs_saves:
        theirs.workflows.save(parent(description))

    reported = status(local_with_history(), client_of(Remote(tmp_path, held=theirs)), PARENT)

    assert relations(reported) == [(PARENT, expected)]


def test_only_what_is_asked_about_is_reported_and_what_neither_holds_is_left_out(
    tmp_path: Path,
) -> None:
    reported = status(
        local_with_history(),
        client_of(Remote(tmp_path)),
        BENCHMARK,
        CHILD,
        CHILD,
    )

    assert relations(reported) == [(CHILD, Relation.LOCAL_ONLY)]


def test_a_workflow_names_the_revision_in_production_at_the_remote(
    tmp_path: Path,
) -> None:
    theirs = local_with_history()
    revision = theirs.workflows.revision(PARENT_ID, 1)

    assert revision is not None

    theirs.production_states.set(
        WorkflowProductionState(specification=revision.specification, specification_revision=1)
    )

    (component,) = status(
        local_with_history(), client_of(Remote(tmp_path, held=theirs)), PARENT
    ).components

    assert (
        component.remote_production_digest == theirs.workflows.lineage(PARENT_ID)[0].revision_digest
    )


# Models


def test_each_model_says_whether_each_side_authorized_it(
    tmp_path: Path,
) -> None:
    local = Instance()
    local.workflows.save(prompting())
    local.portfolio.save(FRONTIER)
    theirs = Instance()
    theirs.portfolio.save(PRIVATE)

    reported = status(local, client_of(Remote(tmp_path, held=theirs)))

    assert reported.models == (
        ModelStatus(
            identifier="openrouter/example/frontier",
            authorized_locally=True,
            authorized_remotely=False,
        ),
        ModelStatus(
            identifier="bedrock/example/private",
            authorized_locally=False,
            authorized_remotely=True,
        ),
    )
    assert reported.portfolio_synced_at == SYNCED


def test_a_model_a_reported_workflow_fixes_is_named_though_neither_side_authorized_it(
    tmp_path: Path,
) -> None:
    local = Instance()
    local.workflows.save(prompting())

    reported = status(local, client_of(Remote(tmp_path)))

    assert [
        (model.identifier, model.authorized_locally, model.authorized_remotely)
        for model in reported.models
    ] == [
        ("openrouter/example/frontier", False, False),
        ("bedrock/example/private", False, False),
    ]
    (tmp_path / "other").mkdir()

    assert status(local, client_of(Remote(tmp_path / "other")), CHILD).models == ()


def test_reaching_the_remote_refreshes_the_snapshot_of_its_portfolio(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.portfolio.save(PRIVATE)
    kept = snapshots()

    status(Instance(), client_of(Remote(tmp_path, held=theirs)), kept=kept)
    snapshot = kept.get(URL)

    assert snapshot is not None
    assert snapshot.synced_at == SYNCED
    assert snapshot.portfolio == PortfolioResponse(
        entries=(PortfolioRecord(identifier="bedrock/example/private"),)
    )


# When the remote cannot be reached


def test_a_remote_not_reached_leaves_its_side_unknown() -> None:
    local = local_with_history()

    reported = status(local, unreachable())

    assert not reported.reachable
    assert relations(reported) == [
        (CHILD, None),
        (PARENT, None),
        (COUNT, None),
        (COUNT_2, None),
        (RUN, None),
    ]
    assert all(component.remote_digest is None for component in reported.components)
    assert reported.portfolio_synced_at is None


def test_a_remote_not_reached_is_read_from_its_last_snapshot() -> None:
    local = Instance()
    local.portfolio.save(FRONTIER)
    kept = snapshots()
    kept.save(
        URL, PortfolioResponse(entries=(PortfolioRecord(identifier="bedrock/example/private"),))
    )

    reported = status(local, unreachable(), kept=kept)

    assert reported.portfolio_synced_at == SYNCED
    assert reported.models == (
        ModelStatus(
            identifier="openrouter/example/frontier",
            authorized_locally=True,
            authorized_remotely=False,
        ),
        ModelStatus(
            identifier="bedrock/example/private", authorized_locally=False, authorized_remotely=True
        ),
    )


def test_with_no_snapshot_whether_the_remote_authorized_a_model_is_unknown() -> None:
    local = Instance()
    local.portfolio.save(FRONTIER)

    (model,) = status(local, unreachable()).models

    assert model == ModelStatus(identifier="openrouter/example/frontier", authorized_locally=True)


# Refusals


def test_a_refused_token_is_an_error_not_an_unknown(
    tmp_path: Path,
) -> None:
    kept = snapshots()

    with pytest.raises(RemoteRefusedError):
        status(Instance(), client_of(Remote(tmp_path), token="azr_unknown"), kept=kept)

    assert kept.get(URL) is None


def test_a_remote_of_another_protocol_is_refused() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"protocol": 2, "azathoth_version": "2.0.0", "schema_version": 9},
        )
    )

    with pytest.raises(ProtocolMismatchError):
        status(
            Instance(),
            RemoteClient(URL, "azr_token", http=httpx.Client(base_url=URL, transport=transport)),
        )
