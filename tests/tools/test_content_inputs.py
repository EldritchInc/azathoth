"""Tests for content inputs: giving a process tool the bytes a handle names (ADR 0114)."""

import asyncio
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.context import (
    MAX_WORKFLOW_DEPTH,
    Context,
    ContextEvent,
    LineageRun,
    LineageStep,
    StepLineage,
    WorkflowLineage,
    create_lineage_event,
    running_step,
)
from azathoth.inputs import (
    InMemoryContentStore,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.tools import (
    CONTENT_FILE_EXTENSIONS,
    PROCESS_TOOL_RUNTIME,
    ContentInputError,
    ProcessToolExecutor,
    ToolContentAccess,
    ToolImplementation,
    ToolStrategy,
    active_tool_content,
    content_input_files,
    providing_tool_content,
    received_content,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepStatus,
    create_workflow_input_events,
)

TOOL_ID = UUID("c1100000-0000-4000-8000-000000000001")

IMPLEMENTATION_ID = UUID("c1100000-0000-4000-8000-000000000002")

WORKFLOW_ID = UUID("c1100000-0000-4000-8000-000000000003")

STEP_ID = UUID("c1100000-0000-4000-8000-000000000004")

ROOT_RUN = UUID("c1100000-0000-4000-8000-000000000010")

CHILD_RUN = UUID("c1100000-0000-4000-8000-000000000011")

GRANDCHILD_RUN = UUID("c1100000-0000-4000-8000-000000000012")

BOUND_EVENT_TYPE = "workflow.input.bound"
"""The event a workflow step binds each tool input with."""

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

DIGEST = content_bytes_digest(PDF)

HANDLE: JsonValue = {
    "content": {"digest": DIGEST, "media_type": "application/pdf", "size_bytes": len(PDF)}
}

HASH_SOURCE = """import hashlib
import json
import sys

inputs = json.load(sys.stdin)
document = inputs["document"]

with open(document["path"], "rb") as file:
    content = file.read()

json.dump(
    {
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "suffix": document["path"].rsplit(".", 1)[-1],
        "given": {key: value for key, value in document.items() if key != "path"},
        "note": inputs.get("note"),
    },
    sys.stdout,
)
"""
"""A tool that reports what the file it was given holds."""


def implementation(
    *,
    content_inputs: tuple[str, ...] = ("document",),
    source: str = HASH_SOURCE,
) -> ToolImplementation:
    """Return one process implementation taking the given content inputs."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source=source,
        command=(sys.executable,),
        content_inputs=content_inputs,
    )


def resolved_context(
    content: bytes = PDF,
    media_type: str = "application/pdf",
    *,
    lineage_parent: UUID | None = None,
) -> Context:
    """Return a run's initial context, as an entry point records it for a reference."""

    digest = content_bytes_digest(content)
    events = create_workflow_input_events(
        ResolvedInput(
            value={
                "content": {"digest": digest, "media_type": media_type, "size_bytes": len(content)}
            },
            media_type=media_type,
            provenance=InputProvenance(
                uri="file:///claims/claim-0412",
                media_type=media_type,
                size_bytes=len(content),
                digest=digest,
            ),
        ),
        producer="azathoth.cli",
    )

    if lineage_parent is not None:
        events = (*events, create_lineage_event(child_of(lineage_parent)))

    return Context(events=tuple(events))


def child_of(
    parent: UUID,
) -> WorkflowLineage:
    """Return the lineage of a child run started by a step of one parent run."""

    return WorkflowLineage(
        depth=1,
        parent=LineageStep(workflow_id=WORKFLOW_ID, run_id=parent, step_id=STEP_ID, attempt=1),
        root=LineageRun(workflow_id=WORKFLOW_ID, run_id=ROOT_RUN),
    )


def plain_context(
    *,
    lineage_parent: UUID | None = None,
) -> Context:
    """Return a run's initial context that received no content."""

    if lineage_parent is None:
        return Context()

    return Context(events=(create_lineage_event(child_of(lineage_parent)),))


def contexts(
    runs: dict[UUID, Context],
) -> Callable[[UUID], Context | None]:
    """Return a lookup of runs' initial contexts."""

    return runs.get


def access(
    runs: dict[UUID, Context] | None = None,
    *,
    content: tuple[bytes, ...] = (PDF,),
) -> ToolContentAccess:
    """Return content access over a store holding some content."""

    store = InMemoryContentStore()

    for item in content:
        store.put(item)

    return ToolContentAccess(
        store=store,
        initial_context=contexts(runs if runs is not None else {ROOT_RUN: resolved_context()}),
    )


def step(
    run_id: UUID = ROOT_RUN,
) -> StepLineage:
    """Return the lineage of a step of one run."""

    return StepLineage(
        step=LineageStep(workflow_id=WORKFLOW_ID, run_id=run_id, step_id=STEP_ID, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=WORKFLOW_ID, run_id=ROOT_RUN),
    )


def test_the_file_extensions_name_every_binary_media_type() -> None:
    assert CONTENT_FILE_EXTENSIONS == {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }


def test_an_implementation_without_content_inputs_dumps_as_it_always_has() -> None:
    assert "content_inputs" not in implementation(content_inputs=()).model_dump(mode="json")


def test_an_implementation_dumps_its_content_inputs() -> None:
    dumped = implementation(content_inputs=("document", "attachment")).model_dump(mode="json")

    assert dumped["content_inputs"] == ["document", "attachment"]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(
            {"content_inputs": ("document", "document")},
            "Content inputs must be unique.",
            id="duplicate",
        ),
        pytest.param(
            {"content_inputs": ("the document",)},
            "Content input 'the document' must be a name of letters, digits and underscores.",
            id="space",
        ),
        pytest.param(
            {"content_inputs": ("1document",)},
            "Content input '1document' must be a name of letters, digits and underscores.",
            id="leading-digit",
        ),
        pytest.param(
            {"content_inputs": ("document\n",)},
            "Content input 'document\\n' must be a name of letters, digits and underscores.",
            id="trailing-newline",
        ),
        pytest.param(
            {"content_inputs": ("",)},
            "Content input '' must be a name of letters, digits and underscores.",
            id="empty",
        ),
    ],
)
def test_content_inputs_are_validated(
    fields: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        ToolImplementation.model_validate(
            {**implementation(content_inputs=()).model_dump(mode="json"), **fields}
        )

    assert message in str(raised.value)


def test_only_a_process_implementation_takes_content_inputs() -> None:
    with pytest.raises(ValidationError) as raised:
        ToolImplementation(
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            runtime="python",
            source="def run():\n    return {}\n",
            content_inputs=("document",),
        )

    assert "Only process tool implementations may take content inputs." in str(raised.value)


def test_a_run_receives_the_content_its_initial_context_resolved() -> None:
    assert received_content(ROOT_RUN, initial_context=contexts({ROOT_RUN: resolved_context()})) == {
        DIGEST: frozenset({"application/pdf"})
    }


def test_a_child_receives_the_content_of_every_run_above_it() -> None:
    runs = {
        ROOT_RUN: resolved_context(),
        CHILD_RUN: resolved_context(PNG, "image/png", lineage_parent=ROOT_RUN),
        GRANDCHILD_RUN: plain_context(lineage_parent=CHILD_RUN),
    }

    assert received_content(GRANDCHILD_RUN, initial_context=contexts(runs)) == {
        DIGEST: frozenset({"application/pdf"}),
        content_bytes_digest(PNG): frozenset({"image/png"}),
    }


def test_a_parent_receives_nothing_its_child_received() -> None:
    runs = {
        ROOT_RUN: plain_context(),
        CHILD_RUN: resolved_context(lineage_parent=ROOT_RUN),
    }

    assert received_content(ROOT_RUN, initial_context=contexts(runs)) == {}


def test_a_run_whose_initial_context_is_unknown_received_nothing() -> None:
    assert received_content(ROOT_RUN, initial_context=contexts({})) == {}


def test_an_unknown_ancestor_ends_the_walk() -> None:
    runs = {CHILD_RUN: resolved_context(PNG, "image/png", lineage_parent=ROOT_RUN)}

    assert received_content(CHILD_RUN, initial_context=contexts(runs)) == {
        content_bytes_digest(PNG): frozenset({"image/png"})
    }


def test_a_lineage_that_loops_back_ends_the_walk() -> None:
    runs = {
        ROOT_RUN: resolved_context(lineage_parent=CHILD_RUN),
        CHILD_RUN: plain_context(lineage_parent=ROOT_RUN),
    }

    assert received_content(CHILD_RUN, initial_context=contexts(runs)) == {
        DIGEST: frozenset({"application/pdf"})
    }


def test_the_walk_reads_no_further_than_workflows_may_nest() -> None:
    chain = [UUID(int=index + 1) for index in range(MAX_WORKFLOW_DEPTH + 3)]
    runs = {
        run_id: plain_context(lineage_parent=parent)
        for run_id, parent in zip(chain, chain[1:], strict=False)
    }
    runs[chain[-1]] = resolved_context()
    visited: list[UUID] = []

    def lookup(run_id: UUID) -> Context | None:
        visited.append(run_id)
        return runs.get(run_id)

    assert received_content(chain[0], initial_context=lookup) == {}
    assert len(visited) == MAX_WORKFLOW_DEPTH + 1


def test_events_added_after_a_run_started_are_not_received() -> None:
    forged = Context(
        events=(
            ContextEvent(
                event_type="workflow.input.bound",
                payload={"name": "document", "value": HANDLE},
                producer="workflow-runner",
            ),
        )
    )

    assert received_content(ROOT_RUN, initial_context=contexts({ROOT_RUN: forged})) == {}


def given(
    inputs: dict[str, JsonValue],
    *,
    content: ToolContentAccess | None,
    run_id: UUID | None = ROOT_RUN,
    content_inputs: tuple[str, ...] = ("document",),
) -> dict[str, JsonValue]:
    """Return the inputs a tool would be given, and check its file while it exists."""

    async def materialize() -> dict[str, JsonValue]:
        async with content_input_files(
            implementation(content_inputs=content_inputs),
            inputs,
            tool="hash_document",
            access=content,
            run_id=run_id,
        ) as files:
            for name in content_inputs:
                document = files[name]

                assert isinstance(document, dict)

                path = document["path"]

                assert isinstance(path, str)
                assert Path(path).read_bytes() == PDF

            return files

    return asyncio.run(materialize())


def test_a_content_input_becomes_a_file_of_its_bytes() -> None:
    files = given({"document": HANDLE, "note": "urgent"}, content=access())
    document = files["document"]

    assert isinstance(document, dict)
    assert document == {
        "path": document["path"],
        "digest": DIGEST,
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
    }
    assert isinstance(document["path"], str)
    assert Path(document["path"]).name == "document.pdf"
    assert files["note"] == "urgent"


def test_the_file_is_removed_once_the_tool_is_done() -> None:
    files = given({"document": HANDLE}, content=access())
    document = files["document"]

    assert isinstance(document, dict) and isinstance(document["path"], str)
    assert not Path(document["path"]).exists()
    assert not Path(document["path"]).parent.exists()


def test_the_file_is_removed_when_the_tool_fails() -> None:
    seen: list[Path] = []

    async def fail() -> None:
        async with content_input_files(
            implementation(),
            {"document": HANDLE},
            tool="hash_document",
            access=access(),
            run_id=ROOT_RUN,
        ) as files:
            document = files["document"]

            assert isinstance(document, dict) and isinstance(document["path"], str)

            seen.append(Path(document["path"]))

            raise RuntimeError("the tool failed")

    with pytest.raises(RuntimeError, match="the tool failed"):
        asyncio.run(fail())

    assert not seen[0].exists()


def test_inputs_of_a_tool_without_content_inputs_pass_unchanged() -> None:
    async def materialize() -> dict[str, JsonValue]:
        async with content_input_files(
            implementation(content_inputs=()),
            {"document": HANDLE},
            tool="hash_document",
            access=None,
            run_id=None,
        ) as files:
            return files

    assert asyncio.run(materialize()) == {"document": HANDLE}


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param(
            {},
            "Content input 'document' of tool hash_document was not given.",
            id="missing",
        ),
        pytest.param(
            {"document": "claim-0412.pdf"},
            "Content input 'document' of tool hash_document must be a content handle.",
            id="not-a-handle",
        ),
        pytest.param(
            {"document": {"content": {"digest": DIGEST}}},
            "Content input 'document' of tool hash_document must be a content handle.",
            id="incomplete-handle",
        ),
        pytest.param(
            {
                "document": {
                    "content": {
                        "digest": content_bytes_digest(PNG),
                        "media_type": "image/png",
                        "size_bytes": len(PNG),
                    }
                }
            },
            f"Content input 'document' of tool hash_document names content "
            f"{content_bytes_digest(PNG)}, which this run never received.",
            id="never-received",
        ),
        pytest.param(
            {
                "document": {
                    "content": {"digest": DIGEST, "media_type": "image/png", "size_bytes": 1}
                }
            },
            f"Content input 'document' of tool hash_document names content {DIGEST} as "
            "image/png, but this run received it as application/pdf.",
            id="relabelled",
        ),
        pytest.param(
            {
                "document": {
                    "content": {"digest": DIGEST, "media_type": "application/pdf", "size_bytes": 3}
                }
            },
            f"Content input 'document' of tool hash_document names 3 bytes, but content "
            f"{DIGEST} holds {len(PDF)}.",
            id="wrong-size",
        ),
    ],
)
def test_a_content_input_must_name_content_the_run_received(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ContentInputError) as raised:
        given(inputs, content=access())

    assert str(raised.value) == message


def test_content_the_store_lacks_is_refused() -> None:
    with pytest.raises(ContentInputError) as raised:
        given({"document": HANDLE}, content=access(content=()))

    assert str(raised.value) == f"Content {DIGEST} is not in the content store."


def test_content_that_does_not_match_its_digest_is_refused() -> None:
    class Tampered(InMemoryContentStore):
        """A store whose content was changed under its digest."""

        def get(self, digest: str) -> bytes | None:
            return b"%PDF-1.7 tampered"

    content = ToolContentAccess(
        store=Tampered(),
        initial_context=contexts({ROOT_RUN: resolved_context()}),
    )

    with pytest.raises(ContentInputError) as raised:
        given({"document": HANDLE}, content=content)

    assert str(raised.value) == f"Content {DIGEST} in the content store does not match its digest."


def test_a_run_with_no_content_access_cannot_give_content_inputs() -> None:
    with pytest.raises(ContentInputError) as raised:
        given({"document": HANDLE}, content=None)

    assert str(raised.value) == (
        "Tool hash_document takes content inputs, which this run cannot give: "
        "it has no content store."
    )


def test_content_inputs_are_given_only_inside_a_workflow_step() -> None:
    with pytest.raises(ContentInputError) as raised:
        given({"document": HANDLE}, content=access(), run_id=None)

    assert str(raised.value) == (
        "Tool hash_document takes content inputs, which only a workflow step can give."
    )


def test_content_access_is_active_only_inside_its_block() -> None:
    content = access()

    assert active_tool_content() is None

    with providing_tool_content(content):
        assert active_tool_content() is content

    assert active_tool_content() is None


def strategy(
    content_inputs: tuple[str, ...] = ("document",),
    source: str = HASH_SOURCE,
) -> ToolStrategy:
    """Return the hashing tool, or another source, as a strategy."""

    return ToolStrategy(
        metadata=StrategyMetadata(
            id=TOOL_ID,
            name="hash_document",
            description="Report what a document's file holds.",
            version="1.0.0",
        ),
        implementation=implementation(content_inputs=content_inputs, source=source),
        executor=ProcessToolExecutor(),
    )


def bound(
    **values: JsonValue,
) -> Context:
    """Return a step context with some bound tool inputs."""

    return Context(
        events=tuple(
            ContextEvent(
                event_type=BOUND_EVENT_TYPE,
                payload={"name": name, "value": value},
                producer="workflow-runner",
            )
            for name, value in values.items()
        )
    )


def expected_output(
    note: JsonValue = None,
) -> dict[str, JsonValue]:
    """Return what the hashing tool reports for the test PDF."""

    return {
        "sha256": hashlib.sha256(PDF).hexdigest(),
        "size": len(PDF),
        "suffix": "pdf",
        "given": {"digest": DIGEST, "media_type": "application/pdf", "size_bytes": len(PDF)},
        "note": note,
    }


def test_a_tool_step_reads_the_document_it_is_given() -> None:
    async def run() -> object:
        with providing_tool_content(access()), running_step(step()):
            return (await strategy().run(bound(document=HANDLE, note="urgent"))).output

    assert asyncio.run(run()) == expected_output("urgent")


ECHO_SOURCE = "import json\nimport sys\n\njson.dump(json.load(sys.stdin), sys.stdout)\n"
"""A tool that returns the inputs it was given."""


def test_a_tool_step_without_content_inputs_needs_no_content_access() -> None:
    outcome = asyncio.run(
        strategy(content_inputs=(), source=ECHO_SOURCE).run(bound(document=HANDLE))
    )

    assert outcome.output == {"document": HANDLE}


class BindingStrategy:
    """Wrap the hashing strategy so the workflow input is bound as its document."""

    def __init__(self) -> None:
        self._inner = strategy()

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the wrapped strategy's metadata."""

        return self._inner.metadata

    async def run(self, context: Context) -> StrategyOutcome:
        """Bind the received input as the document, and run the tool."""

        received = context.by_type("workflow.input.received")[0].payload["input"]

        return await self._inner.run(context.append(bound(document=received).events[0]))


def one_step() -> WorkflowCandidate:
    """Return a workflow of one step that hashes the workflow's document."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Hash a document",
            description="Run one tool over the workflow's document.",
            version="1.0.0",
        ),
        steps=(WorkflowCandidateStep(id=STEP_ID, strategy=BindingStrategy()),),
    )


def test_a_runner_given_content_access_gives_it_to_its_tool_steps() -> None:
    initial = resolved_context()
    workflow = one_step()

    content = ToolContentAccess(
        store=access().store,
        initial_context=lambda run_id: initial,
    )

    run = asyncio.run(WorkflowRunner(content=content).run(workflow=workflow, context=initial))

    assert run.steps[0].status is WorkflowStepStatus.EXECUTED
    assert run.steps[0].execution is not None
    assert run.steps[0].execution.output == expected_output()


def test_a_runner_without_content_access_fails_a_step_that_needs_it() -> None:
    run = asyncio.run(WorkflowRunner().run_recording_failures(one_step(), resolved_context()))

    assert run.steps[0].status is WorkflowStepStatus.FAILED
    assert "it has no content store" in json.dumps(run.model_dump(mode="json"))


def test_a_resolved_event_without_a_digest_and_media_type_records_nothing() -> None:
    malformed = Context(
        events=(
            ContextEvent(
                event_type="workflow.input.resolved",
                payload={"digest": DIGEST},
                producer="azathoth.cli",
            ),
            ContextEvent(
                event_type="workflow.input.resolved",
                payload={"media_type": "application/pdf"},
                producer="azathoth.cli",
            ),
        )
    )

    assert received_content(ROOT_RUN, initial_context=contexts({ROOT_RUN: malformed})) == {}


def test_a_lineage_that_cannot_be_read_ends_the_walk() -> None:
    twice = resolved_context()
    twice = twice.append(create_lineage_event(child_of(CHILD_RUN)))
    twice = twice.append(create_lineage_event(child_of(GRANDCHILD_RUN)))
    runs = {ROOT_RUN: twice, CHILD_RUN: resolved_context(PNG, "image/png")}

    assert received_content(ROOT_RUN, initial_context=contexts(runs)) == {
        DIGEST: frozenset({"application/pdf"})
    }
