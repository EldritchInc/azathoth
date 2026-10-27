"""Tests proving the novel example's edit-queue and write-novel workflows and their tools."""

import json
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.prompting import ContextPromptStrategySpec, PortfolioModelSelection
from azathoth.tools import (
    ToolDocument,
    ToolImplementation,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.examples.test_novel_chapter_examples import LOOP_TOOL_DOCUMENT
from tests.examples.test_novel_revision_examples import (
    ECHO_TOOL_DOCUMENT,
    NOVEL_EXAMPLES,
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

ASSEMBLE_TOOL_DOCUMENT = TOOLS / "assemble-novel.json"

EDIT_QUEUE_WORKFLOW_DOCUMENT = WORKFLOWS / "edit-queue.json"

NOVEL_WORKFLOW_DOCUMENT = WORKFLOWS / "write-novel.json"

REVISION_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000010"

CHAPTER_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000040"

EDIT_QUEUE_WORKFLOW_ID = "e1000000-0000-4000-8000-000000000060"

PICK_STEP_ID = UUID("e1000000-0000-4000-8000-000000000062")

PREPARE_CHAPTERS_STEP_ID = UUID("e1000000-0000-4000-8000-000000000074")

FINAL_EDITS_STEP_ID = UUID("e1000000-0000-4000-8000-000000000077")

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
    ASSEMBLE_TOOL_DOCUMENT,
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
) -> RoutingLanguageModel:
    """Script the story, outline, final review and coherence replies."""

    return RoutingLanguageModel(
        (
            (STORY_MARKER, json.dumps(STORY)),
            (OUTLINE_MARKER, outline(chapters)),
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
) -> tuple[WorkflowRun, JsonValue]:
    """Run the novel workflow with stubbed loops, returning the run and its result."""

    workflow = read_workflow(NOVEL_WORKFLOW_DOCUMENT)

    candidate = generate_novel_candidate(
        workflow,
        model,
        read_tool(ECHO_TOOL_DOCUMENT),
        read_tool(PREPARE_CHAPTERS_TOOL_DOCUMENT),
        read_tool(PREPARE_FINAL_TOOL_DOCUMENT),
        read_tool(ASSEMBLE_TOOL_DOCUMENT),
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
) -> tuple[WorkflowRun, JsonValue]:
    """Run one final-edits pass with a stubbed inner loop, returning the run and its result."""

    workflow = read_workflow(EDIT_QUEUE_WORKFLOW_DOCUMENT)

    candidate = generate_novel_candidate(
        workflow,
        RoutingLanguageModel(()),
        read_tool(ECHO_TOOL_DOCUMENT),
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
    assert isinstance(result, dict)
    assert isinstance(result["chapters"], list)
    assert len(result["chapters"]) == written


def test_chapter_loop_runs_the_example_chapter_workflow_by_default() -> None:
    run, _ = write_novel(novel_model())

    settings = step_value(run, PREPARE_CHAPTERS_STEP_ID, "settings")

    assert isinstance(settings, dict)
    assert settings["workflow_id"] == CHAPTER_WORKFLOW_ID
    assert settings["child_timeout_seconds"] == 1800
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
