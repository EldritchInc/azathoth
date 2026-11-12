"""Tests for saving the revisions a push or pull brings, checked first (ADR 0124)."""

from pathlib import Path

import pytest
from pydantic import JsonValue

from azathoth import __version__
from azathoth.evaluation import BenchmarkDataset, BenchmarkRepository, InMemoryBenchmarkRepository
from azathoth.inputs import ContentRef, InMemoryContentStore, content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import InMemoryModelPortfolioRepository
from azathoth.remote import (
    ACCEPT_RESTRICTED_HINT,
    MAX_CONTENT_BYTES,
    DivergedError,
    PushBundle,
    ReceivedRevision,
    ReceiveRefusedError,
    ReceiveReport,
    RestrictedReceiveRefusedError,
    RevisionRecord,
    receive,
    receive_content,
    restricted_refusal,
)
from azathoth.revisions import Author, Lineage, json_digest, revision_digest
from azathoth.sensitivity import Sensitivity
from azathoth.tools import (
    InMemoryToolRepository,
    ToolDocument,
    ToolDocumentRevision,
    ToolRepository,
)
from azathoth.workflows import (
    InMemoryWorkflowProductionStateRepository,
    InMemoryWorkflowRepository,
    WorkflowRepository,
    WorkflowSpecification,
    WorkflowSpecificationRevision,
)
from tests.remote.test_closure import (
    BENCHMARK,
    BENCHMARK_ID,
    CHILD,
    CHILD_ID,
    COUNT,
    PARENT,
    PARENT_ID,
    RUN,
    SUMMARIZE_STEP,
    Instance,
    case,
    child,
    parent,
    specification,
    tool_step,
)

CHART_BYTES = b"%PDF-1.7 chart of patient 412"

CHART = ContentRef(
    digest=content_bytes_digest(CHART_BYTES),
    media_type="application/pdf",
    size_bytes=len(CHART_BYTES),
)


ERIS = Author(name="Eris", email="eris@example.com")


class Bare(Instance):
    """An instance holding nothing yet, as a fresh remote does."""

    def __init__(self) -> None:
        self.workflows: WorkflowRepository = InMemoryWorkflowRepository()
        self.tools: ToolRepository = InMemoryToolRepository()
        self.benchmarks: BenchmarkRepository = InMemoryBenchmarkRepository()
        self.content = InMemoryContentStore()
        self.production_states = InMemoryWorkflowProductionStateRepository()
        self.portfolio = InMemoryModelPortfolioRepository()


def bundle(
    source: Instance,
    *roots: Lineage,
) -> PushBundle:
    gathered = source.closure(*roots)

    return PushBundle(revisions=gathered.revisions, content=gathered.content)


def received_by(
    target: Instance,
    sent: PushBundle,
    *,
    accepts_restricted: bool = False,
    fork: bool = False,
) -> ReceiveReport:
    return receive(
        sent,
        workflows=target.workflows,
        tools=target.tools,
        benchmarks=target.benchmarks,
        content=target.content,
        accepts_restricted=accepts_restricted,
        fork=fork,
    )


def numbers(
    target: Instance,
    lineage: Lineage,
) -> list[int]:
    return [record.number for record in target.workflows.lineage(lineage.id)]


def local_with_history() -> Instance:
    """Return an instance holding the parent workflow twice, its child and their tools."""

    local = Instance()
    local.workflows.save(child())
    local.workflows.save(parent(), author=ERIS)
    local.workflows.save(parent("Counts again."))

    return local


# Pushing


def test_a_push_to_an_empty_remote_saves_everything_numbered_there() -> None:
    local = local_with_history()
    remote = Bare()
    sent = bundle(local, PARENT)

    report = received_by(remote, sent)

    assert [(saved.lineage, saved.number) for saved in report.received] == [
        (COUNT, 1),
        (RUN, 1),
        (CHILD, 1),
        (PARENT, 1),
        (PARENT, 2),
    ]
    assert [saved.revision_digest for saved in report.received] == [
        record.revision_digest for record in sent.revisions
    ]
    assert (report.already_held, report.forked) == (0, ())
    assert remote.workflows.lineage(PARENT_ID) == local.workflows.lineage(PARENT_ID)
    assert remote.workflows.lineage(PARENT_ID)[0].author == ERIS
    assert remote.workflows.get(PARENT_ID) == parent("Counts again.")


def test_sending_the_same_bundle_again_changes_nothing() -> None:
    local = local_with_history()
    remote = Bare()
    sent = bundle(local, PARENT)

    received_by(remote, sent)

    assert received_by(remote, sent) == ReceiveReport(already_held=5)
    assert numbers(remote, PARENT) == [1, 2]


def test_a_push_moves_the_remote_forward_from_what_it_holds() -> None:
    local = local_with_history()
    remote = Instance()
    remote.workflows.save(child())
    remote.workflows.save(parent())

    report = received_by(remote, bundle(local, PARENT))

    assert report.received == (
        ReceivedRevision(
            lineage=PARENT,
            revision_digest=local.workflows.lineage(PARENT_ID)[1].revision_digest,
            number=2,
        ),
    )
    assert report.already_held == 4
    assert [record.revision_digest for record in remote.workflows.lineage(PARENT_ID)] == [
        record.revision_digest for record in local.workflows.lineage(PARENT_ID)
    ]


def test_a_diverged_lineage_is_refused_and_nothing_is_saved() -> None:
    local = local_with_history()
    local.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "2")))
    remote = Instance()
    remote.workflows.save(child())
    remote.workflows.save(parent())
    theirs = remote.workflows.save(parent("Counts differently."))
    latest = remote.workflows.lineage(PARENT_ID)[-1].revision_digest
    ours = local.workflows.lineage(PARENT_ID)[-1].revision_digest

    with pytest.raises(DivergedError) as caught:
        received_by(remote, bundle(local, CHILD, PARENT))

    assert str(caught.value) == (
        f"Workflow {PARENT_ID} has diverged: its latest revision here, {latest}, is not the one "
        f"revision {ours} builds on. Pull first, then push again."
    )
    assert numbers(remote, PARENT) == [1, 2]
    assert numbers(remote, CHILD) == [1]
    assert remote.workflows.get(PARENT_ID) == theirs.specification


# Pulling


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_a_pull_forks_a_diverged_lineage_on_the_revision_it_builds_on(
    tmp_path: Path,
    backend: str,
) -> None:
    remote = local_with_history()
    local: Instance = Instance()

    if backend == "sqlite":
        repositories = open_repositories(tmp_path / "azathoth.db")
        local.workflows = repositories.workflows
        local.tools = repositories.tools
        local.benchmarks = repositories.benchmarks

    local.workflows.save(child())
    local.workflows.save(parent())
    mine = local.workflows.save(parent("Counts my way."))
    base = local.workflows.lineage(PARENT_ID)[0].revision_digest

    report = received_by(local, bundle(remote, PARENT), fork=True)
    history = local.workflows.lineage(PARENT_ID)

    assert report.forked == (PARENT,)
    assert [saved.number for saved in report.received if saved.lineage == PARENT] == [3]
    assert [record.number for record in history] == [1, 2, 3]
    assert history[2].parent_digest == base
    assert history[2].revision_digest == remote.workflows.lineage(PARENT_ID)[1].revision_digest
    kept = local.workflows.revision(PARENT_ID, 2)

    assert kept is not None
    assert kept.specification == mine.specification


def test_a_pull_of_a_lineage_that_did_not_diverge_forks_nothing() -> None:
    remote = local_with_history()
    local = Instance()
    local.workflows.save(child())
    local.workflows.save(parent())

    report = received_by(local, bundle(remote, PARENT), fork=True)

    assert report.forked == ()
    assert numbers(local, PARENT) == [1, 2]


@pytest.mark.parametrize("fork", [False, True], ids=["push", "pull"])
def test_another_history_of_a_lineage_is_refused(
    fork: bool,
) -> None:
    local = Instance()
    local.workflows.save(child())
    remote = Instance()
    remote.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "9")))
    first = local.workflows.lineage(CHILD_ID)[0].revision_digest

    with pytest.raises(ReceiveRefusedError) as caught:
        received_by(remote, bundle(local, CHILD), fork=fork)

    assert type(caught.value) is ReceiveRefusedError
    assert str(caught.value) == (
        f"Revision {first} of workflow {CHILD_ID} begins its history, but another history of it "
        "is held here."
    )


def test_a_revision_building_on_one_not_held_is_refused() -> None:
    local = local_with_history()
    last = bundle(local, PARENT).revisions[-1]

    with pytest.raises(ReceiveRefusedError) as caught:
        received_by(Bare(), PushBundle(revisions=(last,)))

    assert str(caught.value) == (
        f"Revision {last.revision_digest} of workflow {PARENT_ID} builds on {last.parent_digest}, "
        "which is not held here; send the revisions before it too."
    )


# Reading what was sent


def first_record(
    document: JsonValue,
    lineage: Lineage = CHILD,
) -> RevisionRecord:
    """Return the record of a first revision holding a document as sent."""

    digest = json_digest(document)

    return RevisionRecord(
        lineage=lineage,
        revision_digest=revision_digest(lineage, content_digest=digest, parent_digest=None),
        parent_digest=None,
        content_digest=digest,
        document=document,
    )


def test_a_document_this_azathoth_cannot_read_is_refused() -> None:
    record = first_record({"metadata": {"id": str(CHILD_ID)}})

    with pytest.raises(ReceiveRefusedError) as caught:
        received_by(Bare(), PushBundle(revisions=(record,)))

    assert str(caught.value) == (
        f"Revision {record.revision_digest} of workflow {CHILD_ID} is not a workflow document "
        f"Azathoth {__version__} reads: Field required."
    )


def test_a_document_read_as_other_content_is_refused() -> None:
    document = child().model_dump(mode="json")
    del document["steps"][0]["inputs"]
    record = first_record(document)
    read = json_digest(WorkflowSpecification.model_validate(document).model_dump(mode="json"))

    with pytest.raises(ReceiveRefusedError) as caught:
        received_by(Bare(), PushBundle(revisions=(record,)))

    assert str(caught.value) == (
        f"Azathoth {__version__} reads revision {record.revision_digest} of workflow {CHILD_ID} "
        f"as content {read}, not {record.content_digest}; send it from an Azathoth that reads "
        "it as its digest names."
    )


class RefusingTools(InMemoryToolRepository):
    """A tool repository that refuses every document, as one whose artifact IDs clash would."""

    def save_document(
        self,
        document: ToolDocument,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> ToolDocumentRevision:
        raise ValueError("Artifact 1 belongs to another tool.")


def test_a_revision_the_repository_refuses_is_refused() -> None:
    remote = Bare()
    remote.tools = RefusingTools()
    (record,) = bundle(Instance(), COUNT).revisions

    with pytest.raises(ReceiveRefusedError) as caught:
        received_by(remote, PushBundle(revisions=(record,)))

    assert str(caught.value) == (
        f"Revision {record.revision_digest} of {COUNT} cannot be saved here: Artifact 1 belongs "
        "to another tool."
    )


# Restricted data and content


def charts(
    label: Sensitivity | None,
) -> Instance:
    local = Instance()
    local.benchmarks.save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="charts",
            description="Charts.",
            cases=(case(CHART.to_value(), label),),
        )
    )

    return local


def test_a_remote_that_does_not_accept_restricted_data_refuses_it() -> None:
    remote = Bare()
    remote.content.put(CHART_BYTES)

    with pytest.raises(RestrictedReceiveRefusedError) as caught:
        received_by(remote, bundle(charts(Sensitivity.RESTRICTED), BENCHMARK))

    assert str(caught.value) == (
        "This push carries restricted data, and this remote does not accept restricted data. "
        "Its operator accepts it by starting the remote with "
        "`azathoth remote serve --accept-restricted`."
    )
    assert remote.benchmarks.lineage(BENCHMARK_ID) == ()
    assert ACCEPT_RESTRICTED_HINT in restricted_refusal("Anything")


def test_a_remote_that_accepts_restricted_data_saves_it() -> None:
    remote = Bare()
    remote.content.put(CHART_BYTES)

    report = received_by(
        remote,
        bundle(charts(Sensitivity.RESTRICTED), BENCHMARK),
        accepts_restricted=True,
    )

    assert [saved.lineage for saved in report.received] == [BENCHMARK]


@pytest.mark.parametrize("label", [None, Sensitivity.PUBLIC, Sensitivity.INTERNAL])
def test_other_data_needs_no_acceptance(
    label: Sensitivity | None,
) -> None:
    remote = Bare()
    remote.content.put(CHART_BYTES)

    assert received_by(remote, bundle(charts(label), BENCHMARK)).received


def test_a_benchmark_whose_content_is_not_held_is_refused() -> None:
    remote = Bare()
    sent = bundle(charts(None), BENCHMARK)
    (record,) = sent.revisions

    with pytest.raises(ReceiveRefusedError) as caught:
        received_by(remote, sent)

    assert str(caught.value) == (
        f"Content {CHART.digest}, which revision {record.revision_digest} of benchmark "
        f"{BENCHMARK_ID} holds, is not held here; send it first."
    )
    assert remote.benchmarks.lineage(BENCHMARK_ID) == ()


# Receiving content


def test_content_is_kept_when_it_is_its_digest() -> None:
    store = InMemoryContentStore()

    assert (
        receive_content(
            store,
            CHART_BYTES,
            digest=CHART.digest,
            sensitivity=Sensitivity.INTERNAL,
            accepts_restricted=False,
        )
        == CHART.digest
    )
    assert store.get(CHART.digest) == CHART_BYTES


def test_content_that_is_not_its_digest_is_refused() -> None:
    store = InMemoryContentStore()

    with pytest.raises(ReceiveRefusedError) as caught:
        receive_content(
            store,
            b"other bytes",
            digest=CHART.digest,
            sensitivity=Sensitivity.INTERNAL,
            accepts_restricted=False,
        )

    assert str(caught.value) == (
        f"Content sent as {CHART.digest} is {content_bytes_digest(b'other bytes')}."
    )
    assert not store.contains(CHART.digest)


def test_content_larger_than_a_remote_accepts_is_refused() -> None:
    large = b"x" * (MAX_CONTENT_BYTES + 1)
    store = InMemoryContentStore()

    with pytest.raises(ReceiveRefusedError) as caught:
        receive_content(
            store,
            large,
            digest=content_bytes_digest(large),
            sensitivity=Sensitivity.INTERNAL,
            accepts_restricted=False,
        )

    assert str(caught.value) == (
        f"Content {content_bytes_digest(large)} is {MAX_CONTENT_BYTES + 1} bytes; a remote "
        f"accepts content of at most {MAX_CONTENT_BYTES} bytes."
    )

    exact = b"x" * MAX_CONTENT_BYTES

    assert receive_content(
        store,
        exact,
        digest=content_bytes_digest(exact),
        sensitivity=Sensitivity.INTERNAL,
        accepts_restricted=False,
    )


@pytest.mark.parametrize("accepts", [False, True], ids=["refused", "accepted"])
def test_restricted_content_needs_a_remote_that_accepts_it(
    accepts: bool,
) -> None:
    store = InMemoryContentStore()

    def kept() -> str:
        return receive_content(
            store,
            CHART_BYTES,
            digest=CHART.digest,
            sensitivity=Sensitivity.RESTRICTED,
            accepts_restricted=accepts,
        )

    if accepts:
        assert kept() == CHART.digest
        return

    with pytest.raises(RestrictedReceiveRefusedError) as caught:
        kept()

    assert str(caught.value) == restricted_refusal(f"Content {CHART.digest} is restricted")
    assert not store.contains(CHART.digest)


class RewritingWorkflows(InMemoryWorkflowRepository):
    """A workflow repository that saves something other than it is given."""

    def save(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> WorkflowSpecificationRevision:
        return super().save(
            specification.model_copy(
                update={
                    "metadata": specification.metadata.model_copy(
                        update={"description": "Rewritten."}
                    )
                }
            ),
            author=author,
            based_on=based_on,
        )


def test_a_revision_saved_as_another_is_refused() -> None:
    remote = Bare()
    remote.workflows = RewritingWorkflows()
    (record,) = bundle(local_with_history(), CHILD).revisions

    with pytest.raises(ReceiveRefusedError) as caught:
        received_by(remote, PushBundle(revisions=(record,)))

    assert str(caught.value) == (
        f"Revision {record.revision_digest} of workflow {CHILD_ID} was saved as another revision."
    )
