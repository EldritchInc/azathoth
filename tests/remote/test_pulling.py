"""Tests for what a remote sends for a pull (ADR 0124)."""

import pytest
from pydantic import ValidationError

from azathoth.evaluation import BenchmarkDataset
from azathoth.remote import PullRequest, PullResponse, pull
from azathoth.revisions import Lineage, RevisionKind
from azathoth.sensitivity import Sensitivity
from tests.remote.test_closure import (
    BENCHMARK,
    BENCHMARK_ID,
    PARENT,
    PARENT_ID,
    Instance,
    case,
)
from tests.remote.test_receiving import CHART, local_with_history


def pulled(
    source: Instance,
    *roots: Lineage,
    held: tuple[str, ...] = (),
    include_restricted: bool = False,
) -> PullResponse:
    return pull(
        PullRequest(roots=roots, held=held, include_restricted=include_restricted),
        workflows=source.workflows,
        tools=source.tools,
        benchmarks=source.benchmarks,
    )


def with_benchmark(
    source: Instance,
    *labels: Sensitivity | None,
) -> Instance:
    for label in labels:
        source.benchmarks.save(
            BenchmarkDataset(
                id=BENCHMARK_ID,
                name="charts",
                description=f"Charts, {label}.",
                cases=(case(CHART.to_value(), label),),
            )
        )

    return source


def test_a_pull_sends_the_closure_of_what_it_asks_for() -> None:
    remote = local_with_history()
    response = pulled(remote, PARENT)

    assert response.bundle.revisions == remote.closure(PARENT).revisions
    assert response.unresolved == remote.closure(PARENT).unresolved
    assert response.withheld == ()


def test_revisions_the_client_holds_are_left_out() -> None:
    remote = local_with_history()
    history = remote.workflows.lineage(PARENT_ID)
    everything = remote.closure(PARENT).revisions

    response = pulled(
        remote,
        PARENT,
        held=tuple(record.revision_digest for record in everything[:-1]),
    )

    assert [record.revision_digest for record in response.bundle.revisions] == [
        history[-1].revision_digest
    ]


def test_a_restricted_benchmark_is_withheld_unless_asked_for() -> None:
    remote = with_benchmark(local_with_history(), Sensitivity.RESTRICTED, None)

    response = pulled(remote, BENCHMARK, PARENT)

    assert response.withheld == (BENCHMARK,)
    assert all(
        record.lineage.kind is not RevisionKind.BENCHMARK for record in response.bundle.revisions
    )
    assert response.bundle.content == ()
    assert response.bundle.revisions == remote.closure(PARENT).revisions

    included = pulled(remote, BENCHMARK, include_restricted=True)

    assert included.withheld == ()
    assert [record.lineage for record in included.bundle.revisions] == [BENCHMARK, BENCHMARK]
    assert included.bundle.content[0].sensitivity is Sensitivity.RESTRICTED


def test_other_benchmarks_come_with_their_content() -> None:
    remote = with_benchmark(Instance(), Sensitivity.PUBLIC)

    response = pulled(remote, BENCHMARK)

    assert response.withheld == ()
    assert [record.content.digest for record in response.bundle.content] == [CHART.digest]


def test_a_pull_asks_for_something() -> None:
    with pytest.raises(ValidationError):
        PullRequest(roots=())
