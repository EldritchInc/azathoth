"""Tests for gathering everything a pushed document needs at the remote (ADR 0124)."""

from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkRepository,
    ExpectedOutcome,
    InMemoryBenchmarkRepository,
    OutcomeComparison,
)
from azathoth.inputs import ContentRef, ContentStore, InMemoryContentStore
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import Prompt
from azathoth.remote import (
    CHILD_WORKFLOW_INPUTS,
    RUNTIME,
    Closure,
    ContentRecord,
    ancestry,
    child_workflow_id,
    closure,
    content_refs,
)
from azathoth.revisions import Author, Lineage, RevisionKind
from azathoth.sensitivity import Sensitivity
from azathoth.strategies import StrategyMetadata
from azathoth.tools import InMemoryToolRepository, ToolDocument, ToolRepository, ToolRequirement
from azathoth.workflows import (
    InMemoryWorkflowRepository,
    ToolStepSpecification,
    WorkflowConstantValue,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRepository,
    WorkflowSpecification,
    WorkflowSpecificationRevision,
    WorkflowStepSpecification,
)
from tests.tools.test_catalog import create_tool_definition

PARENT_ID = UUID("c1050000-0000-4000-8000-000000000001")

CHILD_ID = UUID("c1050000-0000-4000-8000-000000000002")

COUNT_ID = UUID("c1050000-0000-4000-8000-000000000011")

RUN_ID = UUID("c1050000-0000-4000-8000-000000000012")

BENCHMARK_ID = UUID("c1050000-0000-4000-8000-000000000021")

COUNT_STEP = UUID("c1050000-0000-4000-8000-000000000031")

CALL_STEP = UUID("c1050000-0000-4000-8000-000000000032")

SUMMARIZE_STEP = UUID("c1050000-0000-4000-8000-000000000033")

ERIS = Author(name="Eris")

CHART = ContentRef(digest="c" * 64, media_type="application/pdf", size_bytes=4)

SCAN = ContentRef(digest="d" * 64, media_type="image/png", size_bytes=8)

ANSWER = ExpectedOutcome(
    description="Answers.",
    value="answer",
    comparison=OutcomeComparison.EXACT,
)


def lineage_of(
    kind: RevisionKind,
    identifier: UUID,
    version: str | None = None,
) -> Lineage:
    return Lineage(kind=kind, id=identifier, version=version)


PARENT = lineage_of(RevisionKind.WORKFLOW, PARENT_ID)

CHILD = lineage_of(RevisionKind.WORKFLOW, CHILD_ID)

COUNT = lineage_of(RevisionKind.TOOL, COUNT_ID, "1.0.0")

COUNT_2 = lineage_of(RevisionKind.TOOL, COUNT_ID, "2.0.0")

RUN = lineage_of(RevisionKind.TOOL, RUN_ID, "1.0.0")

BENCHMARK = lineage_of(RevisionKind.BENCHMARK, BENCHMARK_ID)


def tool_step(
    step_id: UUID,
    name: str,
    version: str | None = None,
    *inputs: WorkflowInputBinding,
) -> WorkflowStepSpecification:
    return WorkflowStepSpecification(
        id=step_id,
        specification=ToolStepSpecification(
            requirement=ToolRequirement(name=name, version=version),
        ),
        inputs=inputs,
    )


def call(
    value: JsonValue,
    name: str = "call",
) -> WorkflowInputBinding:
    return WorkflowInputBinding(name=name, source=WorkflowConstantValue(value=value))


def specification(
    identifier: UUID,
    *steps: WorkflowStepSpecification,
    description: str = "Counts.",
) -> WorkflowSpecification:
    return WorkflowSpecification(
        metadata=WorkflowMetadata(id=identifier, name="workflow", description=description),
        steps=steps,
    )


def parent(
    description: str = "Counts.",
    version: str | None = "1.0.0",
) -> WorkflowSpecification:
    return specification(
        PARENT_ID,
        tool_step(COUNT_STEP, "word_count", version),
        tool_step(
            CALL_STEP,
            "run_workflow",
            "1.0.0",
            call({"workflow_id": str(CHILD_ID), "input": "claim"}),
        ),
        description=description,
    )


def child() -> WorkflowSpecification:
    return specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize"))


def case(
    value: JsonValue,
    label: Sensitivity | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(input=value, expected=ANSWER, sensitivity=label)


class Instance:
    """The repositories of one instance, holding the documents the tests push."""

    def __init__(self) -> None:
        self.workflows: WorkflowRepository = InMemoryWorkflowRepository()
        self.tools: ToolRepository = InMemoryToolRepository()
        self.benchmarks: BenchmarkRepository = InMemoryBenchmarkRepository()
        self.content: ContentStore = InMemoryContentStore()

        for identifier, name, version in (
            (COUNT_ID, "word_count", "1.0.0"),
            (COUNT_ID, "word_count", "2.0.0"),
            (RUN_ID, "run_workflow", "1.0.0"),
        ):
            self.tools.save_document(
                ToolDocument(
                    definition=create_tool_definition(
                        tool_id=identifier,
                        name=name,
                        version=version,
                    )
                )
            )

    def closure(
        self,
        *roots: Lineage,
    ) -> Closure:
        return closure(
            roots,
            workflows=self.workflows,
            tools=self.tools,
            benchmarks=self.benchmarks,
        )


def lineages(
    gathered: Closure,
) -> list[Lineage]:
    return [record.lineage for record in gathered.revisions]


# Workflows


def test_a_workflow_comes_after_its_tools_and_children_with_its_history() -> None:
    instance = Instance()
    instance.workflows.save(child())
    first = instance.workflows.save(parent(), author=ERIS)
    second = instance.workflows.save(parent("Counts again."))

    gathered = instance.closure(PARENT)

    assert lineages(gathered) == [COUNT, RUN, CHILD, PARENT, PARENT]
    assert [record.content_digest for record in gathered.revisions[-2:]] == [
        first.content_digest,
        second.content_digest,
    ]
    assert gathered.revisions[-2].author == ERIS
    assert gathered.revisions[-1].parent_digest == gathered.revisions[-2].revision_digest
    assert gathered.revisions[-1].document == parent("Counts again.").model_dump(mode="json")
    assert gathered.content == ()
    assert gathered.unresolved == (
        f"Step {SUMMARIZE_STEP} of workflow {CHILD_ID} requires tool summarize of any version, "
        "which this instance does not hold.",
    )


def test_a_requirement_without_a_version_needs_every_version() -> None:
    instance = Instance()
    instance.workflows.save(child())
    instance.workflows.save(parent(version=None))

    assert lineages(instance.closure(PARENT))[:3] == [COUNT, COUNT_2, RUN]


def test_only_the_latest_revisions_history_is_pushed() -> None:
    instance = Instance()
    first = instance.workflows.save_revision(child()).lineage
    instance.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "2")))
    instance.workflows.save(
        specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "3")),
        based_on=first.revision_digest,
    )

    gathered = instance.closure(CHILD)
    history = instance.workflows.lineage(CHILD_ID)

    assert [record.revision_digest for record in gathered.revisions] == [
        history[0].revision_digest,
        history[2].revision_digest,
    ]
    assert gathered.unresolved == (
        f"Step {SUMMARIZE_STEP} of workflow {CHILD_ID} requires tool summarize 3, which this "
        "instance does not hold.",
    )


def test_ancestry_follows_parents_from_the_latest() -> None:
    instance = Instance()
    first = instance.workflows.save_revision(child()).lineage
    second = instance.workflows.save_revision(parent()).lineage

    assert ancestry(()) == ()
    assert ancestry((first,)) == (first,)
    assert ancestry((second, first)) == (second,)


def test_a_document_the_instance_does_not_hold_is_named() -> None:
    gathered = Instance().closure(PARENT, BENCHMARK, COUNT_2)

    assert lineages(gathered) == [COUNT_2]
    assert gathered.unresolved == (
        f"This instance holds no workflow {PARENT_ID}.",
        f"This instance holds no benchmark {BENCHMARK_ID}.",
    )


def test_a_child_the_instance_does_not_hold_is_named_once() -> None:
    instance = Instance()
    instance.workflows.save(
        specification(
            PARENT_ID,
            tool_step(CALL_STEP, "run_workflow", "1.0.0", call({"workflow_id": str(CHILD_ID)})),
            tool_step(COUNT_STEP, "run_workflow", "1.0.0", call({"workflow_id": str(CHILD_ID)})),
        )
    )

    gathered = instance.closure(PARENT)

    assert lineages(gathered) == [RUN, PARENT]
    assert gathered.unresolved == (
        f"Step {CALL_STEP} of workflow {PARENT_ID} runs workflow {CHILD_ID}, which this "
        "instance does not hold.",
    )


def test_a_child_named_only_when_its_step_runs_is_named() -> None:
    instance = Instance()
    instance.workflows.save(
        specification(
            PARENT_ID,
            tool_step(
                CALL_STEP,
                "run_workflow",
                "1.0.0",
                WorkflowInputBinding(
                    name="call",
                    source=WorkflowContextReference(
                        event_type="workflow.input.received",
                        field_name="input",
                    ),
                ),
            ),
        )
    )

    assert instance.closure(PARENT).unresolved == (
        f"Step {CALL_STEP} of workflow {PARENT_ID} names its child workflow only when it runs, "
        "so no child is pushed with it.",
    )


def test_shared_dependencies_are_pushed_once() -> None:
    instance = Instance()
    instance.workflows.save(child())
    instance.workflows.save(parent())

    gathered = instance.closure(CHILD, PARENT, COUNT)

    assert lineages(gathered) == [CHILD, COUNT, RUN, PARENT]
    assert len(gathered.unresolved) == 1


# Child workflows


def test_the_standard_tools_name_their_child_in_one_input() -> None:
    assert CHILD_WORKFLOW_INPUTS == {
        "run_workflow": "call",
        "map_workflow": "settings",
        "loop_workflow": "settings",
    }
    assert RUNTIME == "runtime"


@pytest.mark.parametrize(
    ("tool", "binding"),
    [
        ("run_workflow", "call"),
        ("map_workflow", "settings"),
        ("loop_workflow", "settings"),
    ],
)
def test_a_constant_names_the_child(
    tool: str,
    binding: str,
) -> None:
    step = tool_step(CALL_STEP, tool, None, call({"workflow_id": str(CHILD_ID)}, binding))

    assert child_workflow_id(step) == CHILD_ID


@pytest.mark.parametrize(
    "inputs",
    [
        (),
        (call({"workflow_id": str(CHILD_ID)}, "settings"),),
        (call("a workflow"),),
        (call({"input": "claim"}),),
        (call({"workflow_id": 412}),),
        (call({"workflow_id": "not a UUID"}),),
    ],
    ids=["unbound", "other-input", "not-an-object", "unnamed", "numbered", "unparsed"],
)
def test_anything_else_names_the_child_only_when_the_step_runs(
    inputs: tuple[WorkflowInputBinding, ...],
) -> None:
    assert child_workflow_id(tool_step(CALL_STEP, "run_workflow", None, *inputs)) == RUNTIME


def test_other_steps_start_no_child() -> None:
    prompt = WorkflowStepSpecification(
        id=COUNT_STEP,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=SUMMARIZE_STEP,
                name="greet",
                description="Greet.",
                version="1.0.0",
            ),
            prompt=Prompt(text="Say hello."),
            model_selection=FixedModelSelection(provider="test", model="primary"),
        ),
    )

    assert child_workflow_id(prompt) is None
    assert (
        child_workflow_id(
            tool_step(COUNT_STEP, "word_count", None, call({"workflow_id": str(CHILD_ID)}))
        )
        is None
    )


# Benchmarks


def test_a_benchmark_carries_its_cases_content_labelled_by_its_most_sensitive_case() -> None:
    instance = Instance()
    instance.benchmarks.save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="charts",
            description="Charts.",
            cases=(case(CHART.to_value(), Sensitivity.PUBLIC),),
        )
    )
    instance.benchmarks.save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="charts",
            description="Charts.",
            cases=(
                case({"pages": [CHART.to_value(), "text"]}, Sensitivity.RESTRICTED),
                case([{"scan": SCAN.to_value()}]),
            ),
        )
    )

    gathered = instance.closure(BENCHMARK)

    assert lineages(gathered) == [BENCHMARK, BENCHMARK]
    assert gathered.content == (
        ContentRecord(content=CHART, sensitivity=Sensitivity.RESTRICTED),
        ContentRecord(content=SCAN, sensitivity=Sensitivity.INTERNAL),
    )
    assert gathered.revisions[-1].sensitivity is Sensitivity.RESTRICTED


def test_content_handles_are_found_anywhere_in_a_value() -> None:
    assert list(content_refs({"a": [1, {"b": CHART.to_value()}], "c": SCAN.to_value()})) == [
        CHART,
        SCAN,
    ]
    assert list(content_refs({"content": {"digest": "c" * 64}})) == []
    assert list(content_refs("text")) == []


# Revisions that cannot be pushed


class StaleWorkflows(InMemoryWorkflowRepository):
    """Workflow revisions whose stored digest is not their document's, as an older model made."""

    def revision(
        self,
        workflow_id: UUID,
        number: int,
    ) -> WorkflowSpecificationRevision | None:
        held = super().revision(workflow_id, number)

        if held is None or number != 2:
            return held

        return held.model_copy(update={"content_digest": "e" * 64})


class LostWorkflows(InMemoryWorkflowRepository):
    """Workflow revisions whose lineage names a revision that is not held."""

    def revision(
        self,
        workflow_id: UUID,
        number: int,
    ) -> WorkflowSpecificationRevision | None:
        return None


def test_a_revision_that_no_longer_serializes_to_its_digest_is_named() -> None:
    instance = Instance()
    instance.workflows = StaleWorkflows()
    instance.workflows.save(child())
    instance.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "2")))

    gathered = instance.closure(CHILD)

    assert gathered.revisions == ()
    assert gathered.unresolved[-1] == (
        f"Revision 2 of workflow {CHILD_ID} no longer serializes to its content digest "
        f"{'e' * 64}, so it cannot be pushed."
    )


def test_a_revision_that_is_not_held_is_named() -> None:
    instance = Instance()
    instance.workflows = LostWorkflows()
    instance.workflows.save(child())

    assert instance.closure(CHILD) == Closure(
        unresolved=(f"This instance holds no revision 1 of workflow {CHILD_ID}.",)
    )
