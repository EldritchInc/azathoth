"""Tests proving the novel example's edit-queue and write-novel workflows and their tools."""

import json
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.prompting import ContextPromptStrategySpec, PortfolioModelSelection
from azathoth.standard import standard_tool_documents
from azathoth.tools import (
    ToolDocument,
    ToolExecutionError,
    ToolImplementation,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowConstantValue,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepRun,
    WorkflowStepStatus,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.examples.test_novel_chapter_examples import (
    LOOP_TOOL_DOCUMENT,
    constant_input,
    with_constant_input,
)
from tests.examples.test_novel_revision_examples import (
    NOVEL_EXAMPLES,
    SELECT_TOOL_DOCUMENT,
    STANDARD_TOOLS,
    RoutingLanguageModel,
    generate_novel_candidate,
    read_tool,
    read_workflow,
    run_with_input,
)

TOOLS = NOVEL_EXAMPLES / "tools"

WORKFLOWS = NOVEL_EXAMPLES / "workflows"

PICK_TOOL_DOCUMENT = TOOLS / "pick-edit.json"

MERGE_TOOL_DOCUMENT = TOOLS / "merge-edit.json"

PREPARE_CHAPTERS_TOOL_DOCUMENT = TOOLS / "prepare-chapters.json"

PREPARE_FINAL_TOOL_DOCUMENT = TOOLS / "prepare-final-edits.json"

VALIDATE_TOOL_DOCUMENT = STANDARD_TOOLS / "validate-json.json"

JOIN_TOOL_DOCUMENT = STANDARD_TOOLS / "join-text.json"

RENDER_TOOL_DOCUMENT = STANDARD_TOOLS / "render-template.json"

OBJECT_TOOL_DOCUMENT = STANDARD_TOOLS / "json-object.json"

EDIT_QUEUE_WORKFLOW_DOCUMENT = WORKFLOWS / "edit-queue.json"

NOVEL_WORKFLOW_DOCUMENT = WORKFLOWS / "write-novel.json"

REVISION_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000010"

CHAPTER_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000040"

EDIT_QUEUE_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000060"

PICK_STEP_ID = UUID("e1000000-0000-4000-8000-000000000062")

PREPARE_CHAPTERS_STEP_ID = UUID("e1000000-0000-4000-8000-000000000074")

FINAL_EDITS_STEP_ID = UUID("e1000000-0000-4000-8000-000000000077")

PREPARE_FINAL_STEP_ID = UUID("e1000000-0000-4000-8000-000000000078")

VALIDATE_IMPLEMENTATION_ID = "c2000000-0000-4000-8000-000000000044"

CHAPTER_TIMEOUT_SECONDS = 1800

EDIT_TIMEOUT_SECONDS = 1800

LOOP_BUDGET_LIMIT_SECONDS = 86340

LONG_CONTEXT_TOKENS = 200_000

STORY_MARKER = "You are a novelist planning a new novel from an idea"

OUTLINE_MARKER = "You are a novelist outlining a novel chapter by chapter"

REVIEW_MARKER = "doing one last editorial review"

COHERENCE_MARKER = "You are checking a finished novel for coherence"

STORY: JsonValue = {"title": "The Keeper", "premise": "A light keeps the sea asleep."}

COHERENCE_REPORT: JsonValue = {"coherent": True, "issues": []}

STUB_LOOP_SOURCE = """import json
import sys

settings = json.load(sys.stdin)["settings"]
state = dict(settings["state"])
items = []

if "outline" in state:
    items = [
        {
            "number": entry["number"],
            "title": "Chapter " + str(entry["number"]) + " title",
            "text": "Text of chapter " + str(entry["number"]) + ".",
        }
        for entry in state["outline"]
    ]
elif "queue" in state:
    queued = [entry["chapter"] for entry in state["queue"]]
    state["chapters"] = [
        dict(chapter, text="Edited: " + chapter["text"])
        if chapter["number"] in queued
        else chapter
        for chapter in state["chapters"]
    ]
    state["queue"] = []
else:
    state["chapter"] = "Revised: " + state["chapter"]
    state["requests"] = []

json.dump(
    {"items": items, "state": state, "iterations": max(len(items), 1), "completed": True},
    sys.stdout,
)
"""

DOCUMENTS = (
    PICK_TOOL_DOCUMENT,
    MERGE_TOOL_DOCUMENT,
    PREPARE_CHAPTERS_TOOL_DOCUMENT,
    PREPARE_FINAL_TOOL_DOCUMENT,
    EDIT_QUEUE_WORKFLOW_DOCUMENT,
    NOVEL_WORKFLOW_DOCUMENT,
)


def stub_loop_tool() -> ToolDocument:
    """Return the loop tool with an implementation that answers like each example child.

    It recognizes the child by the state it is given: an outline (the chapter
    loop), a queue (the final-edits loop) or a chapter (the inner editing loop).
    """

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


def chapter(
    number: int,
    text: str | None = None,
) -> dict[str, JsonValue]:
    """Return one finished chapter as the chapter loop collects it."""

    return {
        "number": number,
        "title": f"Chapter {number} title",
        "text": text if text is not None else f"Text of chapter {number}.",
    }


def outline(
    count: int,
) -> str:
    """Return a scripted outline reply with the given number of chapters."""

    return json.dumps(
        {
            "chapters": [
                {"number": number, "summary": f"Part {number}."} for number in range(1, count + 1)
            ]
        }
    )


def novel_model(
    *,
    chapters: int = 3,
    edits: JsonValue = None,
    story: JsonValue = STORY,
    outline_reply: str | None = None,
) -> RoutingLanguageModel:
    """Script the story, outline, final review and coherence replies."""

    return RoutingLanguageModel(
        (
            (STORY_MARKER, json.dumps(story)),
            (OUTLINE_MARKER, outline(chapters) if outline_reply is None else outline_reply),
            (REVIEW_MARKER, json.dumps({"edits": edits if edits is not None else []})),
            (COHERENCE_MARKER, json.dumps(COHERENCE_REPORT)),
        )
    )


def step_run(
    run: WorkflowRun,
    step_id: UUID,
) -> WorkflowStepRun:
    """Return the record of one step of a run."""

    return next(step for step in run.steps if step.step_id == step_id)


def step_value(
    run: WorkflowRun,
    step_id: UUID,
    name: str,
) -> JsonValue:
    """Return one value one step of a run recorded."""

    return next(value.value for value in step_run(run, step_id).values if value.name == name)


def write_novel(
    model: RoutingLanguageModel,
    request: dict[str, JsonValue] | None = None,
    *,
    workflow: WorkflowSpecification | None = None,
) -> tuple[WorkflowRun, JsonValue]:
    """Run the novel workflow with stubbed loops, returning the run and its result."""

    if workflow is None:
        workflow = read_workflow(NOVEL_WORKFLOW_DOCUMENT)

    candidate = generate_novel_candidate(
        workflow,
        model,
        read_tool(SELECT_TOOL_DOCUMENT),
        read_tool(PREPARE_CHAPTERS_TOOL_DOCUMENT),
        read_tool(PREPARE_FINAL_TOOL_DOCUMENT),
        read_tool(VALIDATE_TOOL_DOCUMENT),
        read_tool(JOIN_TOOL_DOCUMENT),
        read_tool(RENDER_TOOL_DOCUMENT),
        read_tool(OBJECT_TOOL_DOCUMENT),
        stub_loop_tool(),
    )

    run = run_with_input(
        candidate,
        request if request is not None else {"idea": "A lighthouse that keeps the sea asleep."},
    )

    assert workflow.result is not None

    return run, workflow_result(run, workflow.result, steps=candidate.steps)


def edit_queue(
    queue: list[JsonValue],
    *,
    workflow: WorkflowSpecification | None = None,
) -> tuple[WorkflowRun, JsonValue]:
    """Run one final-edits pass with a stubbed inner loop, returning the run and its result."""

    if workflow is None:
        workflow = read_workflow(EDIT_QUEUE_WORKFLOW_DOCUMENT)

    candidate = generate_novel_candidate(
        workflow,
        RoutingLanguageModel(()),
        read_tool(SELECT_TOOL_DOCUMENT),
        read_tool(PICK_TOOL_DOCUMENT),
        read_tool(MERGE_TOOL_DOCUMENT),
        stub_loop_tool(),
    )

    state: JsonValue = {
        "queue": queue,
        "chapters": [chapter(1), chapter(2), chapter(3)],
        "story": STORY,
        "config": {},
    }

    run = run_with_input(candidate, {"state": state, "iteration": 1})

    assert workflow.result is not None

    return run, workflow_result(run, workflow.result, steps=candidate.steps)


@pytest.mark.parametrize(
    "document",
    [pytest.param(path, id=path.name) for path in DOCUMENTS],
)
def test_novel_example_documents_are_canonical(
    document: Path,
) -> None:
    encoded = document.read_text(encoding="utf-8")

    if document.parent == TOOLS:
        assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")
    else:
        assert encode_workflow_document(decode_workflow_document(encoded)) == encoded.rstrip("\n")


def test_edit_queue_revises_the_next_chapter_and_keeps_going() -> None:
    _, result = edit_queue(
        [
            {"chapter": 2, "requests": ["Fix the tide."]},
            {"chapter": 3, "requests": ["Close the subplot."]},
        ]
    )

    assert result == {
        "state": {
            "queue": [{"chapter": 3, "requests": ["Close the subplot."]}],
            "chapters": [chapter(1), chapter(2, "Revised: Text of chapter 2."), chapter(3)],
            "story": STORY,
            "config": {},
        },
        "done": False,
        "item": 2,
    }


def test_edit_queue_is_done_with_its_last_chapter() -> None:
    _, result = edit_queue([{"chapter": 3, "requests": ["Close the subplot."]}])

    assert isinstance(result, dict)
    assert result["done"] is True
    assert result["item"] == 3


def test_edit_queue_runs_the_example_revision_loop_by_default() -> None:
    run, _ = edit_queue([{"chapter": 2, "requests": ["Fix the tide."]}])

    assert step_value(run, PICK_STEP_ID, "settings") == {
        "workflow_id": REVISION_WORKFLOW_ID,
        "max_iterations": 3,
        "state": {
            "chapter": "Text of chapter 2.",
            "requests": ["Fix the tide."],
            "context": STORY,
        },
    }


def test_novel_is_written_reviewed_edited_checked_and_assembled() -> None:
    _, result = write_novel(novel_model(edits=[{"chapter": 2, "requests": ["Fix the tide."]}]))

    chapters = [chapter(1), chapter(2, "Edited: Text of chapter 2."), chapter(3)]

    assert result == {
        "title": "The Keeper",
        "chapters": chapters,
        "markdown": (
            "# The Keeper\n\n"
            "## Chapter 1: Chapter 1 title\n\nText of chapter 1.\n\n"
            "## Chapter 2: Chapter 2 title\n\nEdited: Text of chapter 2.\n\n"
            "## Chapter 3: Chapter 3 title\n\nText of chapter 3.\n"
        ),
        "report": COHERENCE_REPORT,
    }


def test_final_edits_are_skipped_when_the_review_asks_for_nothing() -> None:
    run, result = write_novel(novel_model())

    assert step_run(run, FINAL_EDITS_STEP_ID).status == WorkflowStepStatus.SKIPPED
    assert isinstance(result, dict)
    assert result["chapters"] == [chapter(1), chapter(2), chapter(3)]


def test_final_review_ignores_unknown_chapters_and_empty_requests() -> None:
    run, result = write_novel(
        novel_model(
            edits=[
                {"chapter": 9, "requests": ["No such chapter."]},
                {"chapter": 1, "requests": []},
            ]
        )
    )

    assert step_run(run, FINAL_EDITS_STEP_ID).status == WorkflowStepStatus.SKIPPED
    assert isinstance(result, dict)
    assert result["chapters"] == [chapter(1), chapter(2), chapter(3)]


@pytest.mark.parametrize(
    ("requested", "planned", "written"),
    [
        pytest.param(None, 20, 18, id="default-cap"),
        pytest.param(5, 20, 5, id="requested-limit"),
        pytest.param(40, 20, 18, id="never-more-than-18"),
        pytest.param(None, 3, 3, id="shorter-story"),
    ],
)
def test_chapter_loop_covers_the_capped_outline(
    requested: int | None,
    planned: int,
    written: int,
) -> None:
    request: dict[str, JsonValue] = {"idea": "A lighthouse."}

    if requested is not None:
        request["max_chapters"] = requested

    run, result = write_novel(novel_model(chapters=planned), request)

    settings = step_value(run, PREPARE_CHAPTERS_STEP_ID, "settings")

    assert isinstance(settings, dict)
    assert settings["max_iterations"] == written
    assert settings["budget_seconds"] == written * CHAPTER_TIMEOUT_SECONDS
    assert isinstance(result, dict)
    assert isinstance(result["chapters"], list)
    assert len(result["chapters"]) == written


def test_chapter_loop_runs_the_example_chapter_workflow_by_default() -> None:
    run, _ = write_novel(novel_model())

    settings = step_value(run, PREPARE_CHAPTERS_STEP_ID, "settings")

    assert isinstance(settings, dict)
    assert settings["workflow_id"] == CHAPTER_WORKFLOW_ID
    assert settings["child_timeout_seconds"] == CHAPTER_TIMEOUT_SECONDS
    assert settings["budget_seconds"] == 3 * CHAPTER_TIMEOUT_SECONDS
    assert settings["state"] == {
        "config": {},
        "story": STORY,
        "outline": json.loads(outline(3))["chapters"],
        "notes": "No chapters have been written yet.",
        "chapter_count": 0,
    }


def test_request_overrides_the_child_workflows_and_revision_settings() -> None:
    run, _ = write_novel(
        novel_model(),
        {
            "idea": "A lighthouse.",
            "chapter_workflow_id": "custom-chapter",
            "revision_workflow_id": "custom-revision",
            "max_revisions": 5,
        },
    )

    settings = step_value(run, PREPARE_CHAPTERS_STEP_ID, "settings")

    assert isinstance(settings, dict)
    assert settings["workflow_id"] == "custom-chapter"
    assert isinstance(settings["state"], dict)
    assert settings["state"]["config"] == {
        "revision_workflow_id": "custom-revision",
        "max_revisions": 5,
    }


def chapter_settings(
    request: dict[str, JsonValue],
    *,
    chapters: int = 3,
) -> dict[str, JsonValue]:
    """Return the chapter loop settings the novel prepares for one request."""

    run, _ = write_novel(novel_model(chapters=chapters), {"idea": "A lighthouse.", **request})

    settings = step_value(run, PREPARE_CHAPTERS_STEP_ID, "settings")

    assert isinstance(settings, dict)

    return settings


def final_edit_settings(
    request: dict[str, JsonValue] | None = None,
    *,
    edits: JsonValue = None,
) -> dict[str, JsonValue]:
    """Return the final-edits loop settings the novel prepares."""

    run, _ = write_novel(
        novel_model(
            edits=edits if edits is not None else [{"chapter": 2, "requests": ["Fix the tide."]}]
        ),
        {"idea": "A lighthouse.", **(request or {})},
    )

    settings = step_value(run, PREPARE_FINAL_STEP_ID, "settings")

    assert isinstance(settings, dict)

    return settings


def test_chapter_budget_follows_a_requested_chapter_timeout() -> None:
    settings = chapter_settings({"chapter_timeout_seconds": 600})

    assert settings["child_timeout_seconds"] == 600
    assert settings["budget_seconds"] == 3 * 600


def test_chapter_budget_never_exceeds_what_the_loop_accepts() -> None:
    settings = chapter_settings({"chapter_timeout_seconds": 6000}, chapters=20)

    assert settings["max_iterations"] == 18
    assert settings["budget_seconds"] == LOOP_BUDGET_LIMIT_SECONDS


def test_request_overrides_the_chapter_budget() -> None:
    settings = chapter_settings({"chapter_budget_seconds": 999})

    assert settings["budget_seconds"] == 999


def test_final_edits_give_each_edit_a_chapters_time() -> None:
    settings = final_edit_settings()

    assert settings["max_iterations"] == 1
    assert settings["child_timeout_seconds"] == EDIT_TIMEOUT_SECONDS
    assert settings["budget_seconds"] == EDIT_TIMEOUT_SECONDS


def test_final_edits_budget_every_queued_edit() -> None:
    settings = final_edit_settings(
        {"edit_timeout_seconds": 900},
        edits=[
            {"chapter": 1, "requests": ["Open on the light."]},
            {"chapter": 3, "requests": ["End at dawn."]},
        ],
    )

    assert settings["max_iterations"] == 2
    assert settings["child_timeout_seconds"] == 900
    assert settings["budget_seconds"] == 2 * 900


def test_request_overrides_the_final_edits_budget() -> None:
    settings = final_edit_settings({"edit_budget_seconds": 42})

    assert settings["budget_seconds"] == 42


@pytest.mark.parametrize(
    ("document", "workflow_id_input", "implementation_id", "implementation_version"),
    [
        pytest.param(
            PREPARE_CHAPTERS_TOOL_DOCUMENT,
            "chapter_workflow_id",
            "e1000000-0000-4000-8000-000000000207",
            "1.2.0",
            id="prepare-chapters",
        ),
        pytest.param(
            PREPARE_FINAL_TOOL_DOCUMENT,
            "edit_queue_workflow_id",
            "e1000000-0000-4000-8000-000000000208",
            "1.2.0",
            id="prepare-final-edits",
        ),
        pytest.param(
            PICK_TOOL_DOCUMENT,
            "revision_workflow_id",
            "e1000000-0000-4000-8000-000000000205",
            "1.1.0",
            id="pick-edit",
        ),
    ],
)
def test_loop_preparation_tools_take_their_child_workflow_as_an_input(
    document: Path,
    workflow_id_input: str,
    implementation_id: str,
    implementation_version: str,
) -> None:
    tool = read_tool(document)
    implementation = tool.implementations[0]

    assert tool.definition.version == "1.1.0"
    required = tool.definition.input_schema.json_schema["required"]

    assert isinstance(required, list)
    assert workflow_id_input in required
    assert implementation.tool_version == "1.1.0"
    assert implementation.version == implementation_version
    assert str(implementation.id) == implementation_id
    assert "e1000000-" not in implementation.source


@pytest.mark.parametrize(
    ("document", "step_id", "name", "workflow_id"),
    [
        pytest.param(
            NOVEL_WORKFLOW_DOCUMENT,
            PREPARE_CHAPTERS_STEP_ID,
            "chapter_workflow_id",
            CHAPTER_WORKFLOW_ID,
            id="chapters",
        ),
        pytest.param(
            NOVEL_WORKFLOW_DOCUMENT,
            PREPARE_FINAL_STEP_ID,
            "edit_queue_workflow_id",
            EDIT_QUEUE_WORKFLOW_ID,
            id="final-edits",
        ),
        pytest.param(
            EDIT_QUEUE_WORKFLOW_DOCUMENT,
            PICK_STEP_ID,
            "revision_workflow_id",
            REVISION_WORKFLOW_ID,
            id="edit-queue",
        ),
    ],
)
def test_novel_workflows_name_their_children_as_constants(
    document: Path,
    step_id: UUID,
    name: str,
    workflow_id: str,
) -> None:
    assert constant_input(read_workflow(document), step_id, name) == WorkflowConstantValue(
        value=workflow_id
    )


def test_chapter_loop_follows_the_workflows_constant() -> None:
    workflow = with_constant_input(
        read_workflow(NOVEL_WORKFLOW_DOCUMENT),
        PREPARE_CHAPTERS_STEP_ID,
        "chapter_workflow_id",
        "another-chapter",
    )

    run, _ = write_novel(novel_model(), workflow=workflow)

    settings = step_value(run, PREPARE_CHAPTERS_STEP_ID, "settings")

    assert isinstance(settings, dict)
    assert settings["workflow_id"] == "another-chapter"


def test_final_edits_loop_follows_the_workflows_constant() -> None:
    workflow = with_constant_input(
        read_workflow(NOVEL_WORKFLOW_DOCUMENT),
        PREPARE_FINAL_STEP_ID,
        "edit_queue_workflow_id",
        "another-edit-queue",
    )

    run, _ = write_novel(
        novel_model(edits=[{"chapter": 2, "requests": ["Fix the tide."]}]),
        workflow=workflow,
    )

    settings = step_value(run, PREPARE_FINAL_STEP_ID, "settings")

    assert isinstance(settings, dict)
    assert settings["workflow_id"] == "another-edit-queue"


def test_edit_queue_revision_loop_follows_the_workflows_constant() -> None:
    workflow = with_constant_input(
        read_workflow(EDIT_QUEUE_WORKFLOW_DOCUMENT),
        PICK_STEP_ID,
        "revision_workflow_id",
        "another-revision",
    )

    run, _ = edit_queue(
        [{"chapter": 2, "requests": ["Fix the tide."]}],
        workflow=workflow,
    )

    settings = step_value(run, PICK_STEP_ID, "settings")

    assert isinstance(settings, dict)
    assert settings["workflow_id"] == "another-revision"


def test_whole_book_steps_require_a_long_context_model() -> None:
    workflow = read_workflow(NOVEL_WORKFLOW_DOCUMENT)

    windows: dict[str, int | None] = {}

    for step in workflow.steps:
        specification = step.specification

        if isinstance(specification, ContextPromptStrategySpec):
            selection = specification.model_selection

            assert isinstance(selection, PortfolioModelSelection)

            windows[specification.metadata.name] = (
                selection.requirements.minimum_context_window_tokens
            )

    assert windows == {
        "Plan story": None,
        "Plan chapters": None,
        "Final review": LONG_CONTEXT_TOKENS,
        "Check coherence": LONG_CONTEXT_TOKENS,
    }


def test_whole_book_prompts_read_the_finished_chapters() -> None:
    model = novel_model(edits=[{"chapter": 2, "requests": ["Fix the tide."]}])

    write_novel(model)

    (review_prompt,) = model.prompts_containing(REVIEW_MARKER)
    (coherence_prompt,) = model.prompts_containing(COHERENCE_MARKER)

    assert "Text of chapter 2." in review_prompt
    assert "Edited: Text of chapter 2." in coherence_prompt


def rejected_plan(
    model: RoutingLanguageModel,
) -> str:
    """Run the novel workflow with a model whose plan must be rejected; return the error."""

    workflow = read_workflow(NOVEL_WORKFLOW_DOCUMENT)

    candidate = generate_novel_candidate(
        workflow,
        model,
        read_tool(SELECT_TOOL_DOCUMENT),
        read_tool(PREPARE_CHAPTERS_TOOL_DOCUMENT),
        read_tool(PREPARE_FINAL_TOOL_DOCUMENT),
        read_tool(VALIDATE_TOOL_DOCUMENT),
        read_tool(JOIN_TOOL_DOCUMENT),
        read_tool(RENDER_TOOL_DOCUMENT),
        read_tool(OBJECT_TOOL_DOCUMENT),
        stub_loop_tool(),
    )

    with pytest.raises(ToolExecutionError) as error:
        run_with_input(candidate, {"idea": "A lighthouse."})

    return str(error.value)


def test_a_story_plan_without_a_title_stops_the_novel() -> None:
    model = novel_model(story={"premise": "A light keeps the sea asleep."})

    assert rejected_plan(model) == (
        f"Tool implementation {VALIDATE_IMPLEMENTATION_ID} exited with status 1: "
        "validate_json rejected the value at $: 'title' is a required property."
    )
    assert model.prompts_containing(OUTLINE_MARKER) == ()


def test_a_story_plan_with_a_nameless_character_stops_the_novel() -> None:
    model = novel_model(
        story={
            "title": "The Keeper",
            "premise": "A light keeps the sea asleep.",
            "characters": [{"role": "keeper"}],
        }
    )

    assert rejected_plan(model).endswith(
        "validate_json rejected the value at $.characters[0]: 'name' is a required property."
    )


def test_an_empty_outline_stops_the_novel_before_any_chapter() -> None:
    model = novel_model(outline_reply='{"chapters": []}')

    assert rejected_plan(model).endswith(
        "validate_json rejected the value at $: [] should be non-empty."
    )
    assert model.prompts_containing(REVIEW_MARKER) == ()


def test_an_outline_entry_without_a_summary_stops_the_novel() -> None:
    model = novel_model(outline_reply='{"chapters": [{"number": 1}]}')

    assert rejected_plan(model).endswith(
        "validate_json rejected the value at $[0]: 'summary' is a required property."
    )


def test_the_novel_shapes_its_values_with_the_standard_tools() -> None:
    standard = {document.definition.name for document in standard_tool_documents()}

    tools = sorted(
        step.specification.requirement.name
        for path in sorted(WORKFLOWS.glob("*.json"))
        for step in read_workflow(path).steps
        if isinstance(step.specification, ToolStepSpecification)
        and step.specification.requirement.name in standard
    )

    assert tools == [
        "join_text",
        "json_object",
        "json_select",
        "json_select",
        "json_select",
        "json_select",
        "loop_workflow",
        "loop_workflow",
        "loop_workflow",
        "loop_workflow",
        "render_template",
        "validate_json",
        "validate_json",
    ]
    assert sorted(path.name for path in TOOLS.glob("*.json")) == [
        "finalize-chapter.json",
        "merge-edit.json",
        "pack-revision.json",
        "pick-edit.json",
        "prepare-chapters.json",
        "prepare-final-edits.json",
        "prepare-revision.json",
    ]


def test_the_readme_shows_the_real_rejection_of_a_plan() -> None:
    message = rejected_plan(novel_model(story={"premise": "A light keeps the sea asleep."}))

    readme = NOVEL_EXAMPLES / "README.md"

    assert f"\n{message}\n" in readme.read_text(encoding="utf-8")
