"""Tests proving the novel example's write-chapter workflow and its tools."""

import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.tools import (
    ToolDocument,
    ToolImplementation,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    WorkflowConstantValue,
    WorkflowNamedValueReference,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepRun,
    WorkflowStepStatus,
    WorkflowValueReference,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.examples.test_novel_revision_examples import (
    ECHO_TOOL_DOCUMENT,
    NOVEL_EXAMPLES,
    RoutingLanguageModel,
    generate_novel_candidate,
    read_tool,
    read_workflow,
    run_with_input,
)

LOOP_TOOL_DOCUMENT = (
    Path(__file__).parents[2] / "src" / "azathoth" / "standard" / "tools" / "loop-workflow.json"
)

PREPARE_TOOL_DOCUMENT = NOVEL_EXAMPLES / "tools" / "prepare-revision.json"

FINALIZE_TOOL_DOCUMENT = NOVEL_EXAMPLES / "tools" / "finalize-chapter.json"

CHAPTER_WORKFLOW_DOCUMENT = NOVEL_EXAMPLES / "workflows" / "write-chapter.json"

REVISION_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000010"

REVISE_STEP_ID = UUID("e1000000-0000-4000-8000-000000000044")

PREPARE_STEP_ID = UUID("e1000000-0000-4000-8000-000000000045")

DRAFT_MARKER = "You are a novelist writing a novel one chapter at a time"

REVIEW_MARKER = "You are the editor of a novel, reviewing one newly drafted chapter"

NOTES_MARKER = "You keep the continuity notes for a novel"

DRAFT = "Mara climbed the stairs of Saint Elmo's Light."

STORY: JsonValue = {"title": "The Keeper", "premise": "A light keeps the sea asleep."}

OUTLINE: JsonValue = [
    {"number": 1, "summary": "Mara arrives."},
    {"number": 2, "summary": "The lamp fails."},
    {"number": 3, "summary": "The sea wakes."},
]

STUB_LOOP_SOURCE = """import json
import sys

settings = json.load(sys.stdin)["settings"]
state = settings["state"]

json.dump(
    {
        "items": [0],
        "state": {
            "chapter": "Revised: " + state["chapter"],
            "requests": [],
            "context": state["context"],
        },
        "iterations": 1,
        "completed": True,
    },
    sys.stdout,
)
"""


def stub_loop_tool() -> ToolDocument:
    """Return the loop tool with an implementation that answers without invoking children."""

    document = read_tool(LOOP_TOOL_DOCUMENT)

    implementation = ToolImplementation.model_validate(
        {
            **document.implementations[0].model_dump(),
            "source": STUB_LOOP_SOURCE,
            "command": [sys.executable],
        }
    )

    return ToolDocument.model_validate(
        {
            **dict(document),
            "implementations": (implementation,),
        }
    )


def chapter_model(
    requests: str = '{"requests": []}',
    *,
    story_complete: bool = False,
) -> RoutingLanguageModel:
    """Script the drafting, editorial and continuity replies for one chapter."""

    complete = "true" if story_complete else "false"

    return RoutingLanguageModel(
        (
            (DRAFT_MARKER, DRAFT),
            (REVIEW_MARKER, requests),
            (
                NOTES_MARKER,
                '{"notes": "Mara is at the lighthouse.", "title": "Arrival", '
                f'"story_complete": {complete}}}',
            ),
        )
    )


def with_constant_input(
    workflow: WorkflowSpecification,
    step_id: UUID,
    name: str,
    value: JsonValue,
) -> WorkflowSpecification:
    """Return the workflow with one step's named input bound to another constant."""

    steps = tuple(
        step.model_copy(
            update={
                "inputs": tuple(
                    binding.model_copy(update={"source": WorkflowConstantValue(value=value)})
                    if binding.name == name
                    else binding
                    for binding in step.inputs
                )
            }
        )
        if step.id == step_id
        else step
        for step in workflow.steps
    )

    return workflow.model_copy(update={"steps": steps})


def constant_input(
    workflow: WorkflowSpecification,
    step_id: UUID,
    name: str,
) -> object:
    """Return the source one step binds to one named input."""

    (step,) = (step for step in workflow.steps if step.id == step_id)
    (binding,) = (binding for binding in step.inputs if binding.name == name)

    return binding.source


def write_chapter(
    model: RoutingLanguageModel,
    *,
    number: int = 1,
    config: JsonValue = None,
    workflow: WorkflowSpecification | None = None,
) -> tuple[WorkflowRun, JsonValue]:
    """Run one chapter pass with a stubbed inner loop, returning the run and its result."""

    if workflow is None:
        workflow = read_workflow(CHAPTER_WORKFLOW_DOCUMENT)

    candidate = generate_novel_candidate(
        workflow,
        model,
        read_tool(ECHO_TOOL_DOCUMENT),
        read_tool(PREPARE_TOOL_DOCUMENT),
        read_tool(FINALIZE_TOOL_DOCUMENT),
        stub_loop_tool(),
    )

    state: dict[str, JsonValue] = {
        "story": STORY,
        "outline": OUTLINE,
        "notes": "No chapters have been written yet.",
        "chapter_count": number - 1,
    }

    if config is not None:
        state["config"] = config

    run = run_with_input(candidate, {"state": state, "iteration": number})

    assert workflow.result is not None

    return run, workflow_result(run, workflow.result, steps=candidate.steps)


def step_run(
    run: WorkflowRun,
    step_id: UUID,
) -> WorkflowStepRun:
    """Return the record of one step of a run.

    Runs record steps in execution order, layer by layer, not in declared order.
    """

    return next(step for step in run.steps if step.step_id == step_id)


def step_run_values(
    run: WorkflowRun,
    step_id: UUID,
) -> dict[str, JsonValue]:
    """Return the values one step of a run recorded, by name."""

    return {value.name: value.value for value in step_run(run, step_id).values}


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(PREPARE_TOOL_DOCUMENT, id="prepare-revision"),
        pytest.param(FINALIZE_TOOL_DOCUMENT, id="finalize-chapter"),
    ],
)
def test_chapter_tool_examples_are_canonical(
    path: Path,
) -> None:
    encoded = path.read_text(encoding="utf-8")

    assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")


def test_write_chapter_workflow_example_is_canonical() -> None:
    encoded = CHAPTER_WORKFLOW_DOCUMENT.read_text(encoding="utf-8")

    assert encode_workflow_document(decode_workflow_document(encoded)) == encoded.rstrip("\n")


def test_revision_runs_only_when_the_editor_asks_for_changes() -> None:
    steps = read_workflow(CHAPTER_WORKFLOW_DOCUMENT).steps

    revise, prepare = steps[3], steps[4]

    assert revise.depends_on == (prepare.id,)
    assert len(revise.conditions) == 1
    assert revise.conditions[0].source == WorkflowValueReference(
        producer_step_id=prepare.id,
        name="needs_revision",
    )
    assert revise.conditions[0].expected is True


def test_finished_chapter_prefers_the_revision_over_the_draft() -> None:
    steps = read_workflow(CHAPTER_WORKFLOW_DOCUMENT).steps

    revise, prepare, notes, finalize = steps[3], steps[4], steps[5], steps[6]

    for consumer in (notes, finalize):
        chapter_input = next(binding for binding in consumer.inputs if binding.name == "chapter")

        assert chapter_input.source == WorkflowNamedValueReference(name="chapter")
        assert {revise.id, prepare.id} <= set(consumer.depends_on)

    assert steps.index(revise) < steps.index(prepare)


def test_chapter_without_requested_changes_keeps_its_draft() -> None:
    run, result = write_chapter(chapter_model())

    assert step_run(run, REVISE_STEP_ID).status == WorkflowStepStatus.SKIPPED
    assert result == {
        "state": {
            "story": STORY,
            "outline": OUTLINE,
            "notes": "Mara is at the lighthouse.",
            "chapter_count": 1,
        },
        "done": False,
        "item": {"number": 1, "title": "Arrival", "text": DRAFT},
    }


def test_chapter_with_requested_changes_uses_the_inner_loop_revision() -> None:
    model = chapter_model('{"requests": ["Name the lighthouse keeper."]}')

    run, result = write_chapter(model)

    assert step_run(run, REVISE_STEP_ID).status == WorkflowStepStatus.EXECUTED
    assert isinstance(result, dict)
    assert result["item"] == {"number": 1, "title": "Arrival", "text": f"Revised: {DRAFT}"}

    (notes_prompt,) = model.prompts_containing(NOTES_MARKER)

    assert f"Revised: {DRAFT}" in notes_prompt


def test_inner_loop_settings_default_to_the_example_revision_workflow() -> None:
    run, _ = write_chapter(chapter_model('{"requests": ["Name the lighthouse keeper."]}'))

    settings = step_run_values(run, PREPARE_STEP_ID)["settings"]

    assert settings == {
        "workflow_id": REVISION_WORKFLOW_ID,
        "max_iterations": 3,
        "state": {
            "chapter": DRAFT,
            "requests": ["Name the lighthouse keeper."],
            "context": STORY,
        },
    }


def test_loop_state_config_overrides_the_inner_loop_settings() -> None:
    run, _ = write_chapter(
        chapter_model('{"requests": ["Name the lighthouse keeper."]}'),
        config={"revision_workflow_id": "custom-revision", "max_revisions": 5},
    )

    settings = step_run_values(run, PREPARE_STEP_ID)["settings"]

    assert isinstance(settings, dict)
    assert (settings["workflow_id"], settings["max_iterations"]) == ("custom-revision", 5)


def test_chapter_loop_is_done_when_the_story_ends() -> None:
    _, result = write_chapter(chapter_model(story_complete=True))

    assert isinstance(result, dict)
    assert result["done"] is True


def test_chapter_loop_is_done_when_the_outline_runs_out() -> None:
    _, result = write_chapter(chapter_model(), number=3)

    assert isinstance(result, dict)
    assert result["done"] is True
    assert result["item"] == {"number": 3, "title": "Arrival", "text": DRAFT}


def test_draft_prompt_carries_the_story_outline_notes_and_number() -> None:
    model = chapter_model()

    write_chapter(model, number=2)

    (draft_prompt,) = model.prompts_containing(DRAFT_MARKER)

    assert '"title":"The Keeper"' in draft_prompt
    assert '"summary":"The lamp fails."' in draft_prompt
    assert "No chapters have been written yet." in draft_prompt
    assert "Write chapter 2 so that" in draft_prompt


def test_chapter_names_its_revision_workflow_as_a_constant() -> None:
    workflow = read_workflow(CHAPTER_WORKFLOW_DOCUMENT)

    assert constant_input(workflow, PREPARE_STEP_ID, "revision_workflow_id") == (
        WorkflowConstantValue(value=REVISION_WORKFLOW_ID)
    )


def test_inner_loop_follows_the_workflows_constant() -> None:
    workflow = with_constant_input(
        read_workflow(CHAPTER_WORKFLOW_DOCUMENT),
        PREPARE_STEP_ID,
        "revision_workflow_id",
        "another-revision",
    )

    run, _ = write_chapter(
        chapter_model('{"requests": ["Name the lighthouse keeper."]}'),
        workflow=workflow,
    )

    settings = step_run_values(run, PREPARE_STEP_ID)["settings"]

    assert isinstance(settings, dict)
    assert settings["workflow_id"] == "another-revision"


def test_prepare_revision_takes_its_workflow_id_as_an_input() -> None:
    tool = read_tool(PREPARE_TOOL_DOCUMENT)
    implementation = tool.implementations[0]

    assert tool.definition.version == "1.1.0"
    required = tool.definition.input_schema.json_schema["required"]

    assert isinstance(required, list)
    assert "revision_workflow_id" in required
    assert (implementation.tool_version, implementation.version) == ("1.1.0", "1.1.0")
    assert str(implementation.id) == "e1000000-0000-4000-8000-000000000203"
    assert "e1000000-" not in implementation.source
