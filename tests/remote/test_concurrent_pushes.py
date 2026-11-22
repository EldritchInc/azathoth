"""Tests that two pushes of one lineage arriving together never fork it silently (ADR 0135).

A push is checked against the lineage's latest revision before anything is
saved. Another push may save a revision between that check and the save,
so the first new revision of each lineage is saved fast-forward only: the
repository checks again, in the transaction that saves it.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from azathoth.evaluation import BenchmarkDataset, InMemoryBenchmarkRepository
from azathoth.remote import DivergedError, PushBundle
from azathoth.revisions import Author, Lineage, NotFastForwardError, RevisionKind
from azathoth.tools import InMemoryToolRepository, ToolDocument
from azathoth.workflows import (
    InMemoryWorkflowRepository,
    WorkflowSpecification,
    WorkflowSpecificationRevision,
)
from tests.remote.test_closure import (
    BENCHMARK_ID,
    CHILD_ID,
    COUNT_ID,
    PARENT,
    PARENT_ID,
    case,
    parent,
)
from tests.remote.test_receiving import Bare, bundle, local_with_history, received_by
from tests.tools.test_catalog import create_tool_definition


class Interleaved(InMemoryWorkflowRepository):
    """A workflow repository that lets another push in just before its next save."""

    def __init__(self) -> None:
        super().__init__()
        self.meanwhile: Callable[[], object] | None = None

    def save(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
        fast_forward: bool = False,
    ) -> WorkflowSpecificationRevision:
        meanwhile, self.meanwhile = self.meanwhile, None

        if meanwhile is not None:
            meanwhile()

        return super().save(
            specification,
            author=author,
            based_on=based_on,
            fast_forward=fast_forward,
        )


def remote_with_history() -> tuple[Bare, Interleaved]:
    """Return a remote holding the history both pushes build on, and its workflows."""

    remote = Bare()
    workflows = Interleaved()
    remote.workflows = workflows
    received_by(remote, bundle(local_with_history(), PARENT))

    return remote, workflows


def changed(
    description: str,
) -> PushBundle:
    """Return a push of one new revision of the parent, built on the shared history."""

    local = local_with_history()
    local.workflows.save(parent(description))

    return bundle(local, PARENT)


def test_a_push_overtaken_by_another_is_told_it_diverged_and_saves_nothing() -> None:
    remote, workflows = remote_with_history()
    ours, theirs = changed("Ours."), changed("Theirs.")
    taken: list[object] = []
    workflows.meanwhile = lambda: taken.append(received_by(remote, theirs))
    their_digest = theirs.revisions[-1].revision_digest

    with pytest.raises(DivergedError) as caught:
        received_by(remote, ours)

    history = remote.workflows.lineage(PARENT_ID)

    assert len(taken) == 1
    assert [record.number for record in history] == [1, 2, 3]
    assert history[-1].revision_digest == their_digest
    assert history[-1].parent_digest == history[-2].revision_digest
    assert str(caught.value) == (
        f"Workflow {PARENT_ID} has diverged: its latest revision here, {their_digest}, is not "
        f"the one revision {ours.revisions[-1].revision_digest} builds on. Pull first, then "
        "push again."
    )


def test_a_push_overtaken_by_the_same_revision_finds_it_held() -> None:
    remote, workflows = remote_with_history()
    ours, theirs = changed("Same."), changed("Same.")
    workflows.meanwhile = lambda: received_by(remote, theirs)

    report = received_by(remote, ours)
    history = remote.workflows.lineage(PARENT_ID)

    received = [
        (saved.revision_digest, saved.number)
        for saved in report.received
        if saved.lineage == PARENT
    ]

    assert [record.number for record in history] == [1, 2, 3]
    assert received == [(history[-1].revision_digest, 3)]


def test_a_pull_that_forks_is_never_refused_for_it() -> None:
    remote, workflows = remote_with_history()
    ours, theirs = changed("Ours."), changed("Theirs.")
    workflows.meanwhile = lambda: received_by(remote, theirs)

    report = received_by(remote, ours, fork=True)
    history = remote.workflows.lineage(PARENT_ID)

    assert [record.number for record in history] == [1, 2, 3, 4]
    assert history[2].parent_digest == history[3].parent_digest == history[1].revision_digest
    assert report.received[-1].number == 4


# Fast-forward only, in each repository


def test_a_workflow_saved_fast_forward_only_must_build_on_the_latest() -> None:
    workflows = InMemoryWorkflowRepository()
    workflows.save(parent())
    (first,) = workflows.lineage(PARENT_ID)
    workflows.save(parent("Again."))
    (_, latest) = workflows.lineage(PARENT_ID)

    with pytest.raises(NotFastForwardError) as caught:
        workflows.save(parent("Late."), based_on=first.revision_digest, fast_forward=True)

    assert str(caught.value) == (
        f"A revision of workflow {PARENT_ID} builds on revision {first.revision_digest}, but its "
        f"latest is now revision {latest.revision_digest}."
    )
    assert len(workflows.lineage(PARENT_ID)) == 2

    workflows.save(parent("On time."), based_on=latest.revision_digest, fast_forward=True)

    assert len(workflows.lineage(PARENT_ID)) == 3


def test_a_first_revision_saved_fast_forward_only_needs_an_empty_history() -> None:
    workflows = InMemoryWorkflowRepository()
    workflows.save(parent(), fast_forward=True)

    with pytest.raises(NotFastForwardError, match="builds on nothing, but its latest is now"):
        workflows.save(parent("Another first."), fast_forward=True)

    assert len(workflows.lineage(PARENT_ID)) == 1
    assert workflows.lineage(CHILD_ID) == ()


def test_a_tool_version_saved_fast_forward_only_must_build_on_the_latest() -> None:
    tools = InMemoryToolRepository()
    lineage = Lineage(kind=RevisionKind.TOOL, id=COUNT_ID, version="1.0.0")

    def document(
        description: str,
    ) -> ToolDocument:
        return ToolDocument(
            definition=create_tool_definition(
                tool_id=COUNT_ID,
                name="word_count",
                version="1.0.0",
            ).model_copy(update={"description": description})
        )

    tools.save_document(document("Counts."))
    (first,) = tools.document_lineage(COUNT_ID, "1.0.0")
    tools.save_document(document("Counts again."))

    with pytest.raises(NotFastForwardError) as caught:
        tools.save_document(
            document("Late."),
            based_on=first.revision_digest,
            fast_forward=True,
        )

    assert caught.value.lineage == lineage
    assert len(tools.document_lineage(COUNT_ID, "1.0.0")) == 2


def test_a_benchmark_saved_fast_forward_only_must_build_on_the_latest() -> None:
    benchmarks = InMemoryBenchmarkRepository()

    def dataset(
        description: str,
    ) -> BenchmarkDataset:
        return BenchmarkDataset(
            id=BENCHMARK_ID,
            name="charts",
            description=description,
            cases=(case("chart"),),
        )

    benchmarks.save(dataset("Charts."))
    (first,) = benchmarks.lineage(BENCHMARK_ID)
    benchmarks.save(dataset("Charts again."))

    with pytest.raises(NotFastForwardError):
        benchmarks.save(dataset("Late."), based_on=first.revision_digest, fast_forward=True)

    assert len(benchmarks.lineage(BENCHMARK_ID)) == 2


def test_saving_without_fast_forward_still_forks() -> None:
    workflows = InMemoryWorkflowRepository()
    workflows.save(parent())
    (first,) = workflows.lineage(PARENT_ID)
    workflows.save(parent("Again."))
    workflows.save(parent("A fork."), based_on=first.revision_digest)

    history = workflows.lineage(PARENT_ID)

    assert [record.number for record in history] == [1, 2, 3]
    assert history[2].parent_digest == first.revision_digest


def test_the_revisions_readme_quotes_the_refusal_of_a_save_that_is_not_a_fast_forward() -> None:
    readme = Path(__file__).parents[2] / "src" / "azathoth" / "revisions" / "README.md"
    refusal = str(
        NotFastForwardError(
            Lineage(kind=RevisionKind.WORKFLOW, id=PARENT_ID),
            latest="b" * 64,
            based_on="a" * 64,
        )
    )
    template = (
        refusal.replace(str(PARENT_ID), "<WORKFLOW_ID>")
        .replace("a" * 64, "<DIGEST>")
        .replace("b" * 64, "<LATEST>")
    )

    assert f"\n{template}\n" in readme.read_text(encoding="utf-8")
