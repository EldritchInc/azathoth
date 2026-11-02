"""Tests proving the map example and its walkthrough (ADR 0106)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowConstantValue,
    decode_workflow_document,
    encode_workflow_document,
)
from tests.examples.test_word_count_benchmark_examples import configure_walkthrough, run_cli

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOW_EXAMPLES = PROJECT_ROOT / "examples" / "workflows"

CHILD_DOCUMENT = WORKFLOW_EXAMPLES / "count-words-in-item.json"

MAP_DOCUMENT = WORKFLOW_EXAMPLES / "map-word-count.json"

PROCESS_TOOL_DOCUMENT = PROJECT_ROOT / "examples" / "tools" / "word-count-process.json"

CHILD_WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000006")

MAP_WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000007")

MAP_STEP_ID = UUID("a1000000-0000-4000-8000-000000000071")

TEXTS = '["the old ones wait", "and dream", "in sunken cities"]'

MAPPED = '[{"result": 4}, {"result": 2}, {"result": 3}]'

GUIDES = (
    PROJECT_ROOT / "docs" / "examples.md",
    WORKFLOW_EXAMPLES / "README.md",
)


@pytest.fixture
def walkthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import the map example's documents and promote its child; return the database."""

    database = configure_walkthrough(monkeypatch, tmp_path)

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)

    run_cli(capsys, "tool", "import", str(PROCESS_TOOL_DOCUMENT))
    run_cli(capsys, "tool", "install-standard")
    run_cli(capsys, "workflow", "import", str(CHILD_DOCUMENT))
    run_cli(capsys, "workflow", "import", str(MAP_DOCUMENT))
    run_cli(capsys, "workflow", "promote", str(CHILD_WORKFLOW_ID))

    return database


def run_map(
    capsys: pytest.CaptureFixture[str],
    texts: str = TEXTS,
) -> tuple[int, str, str]:
    """Run the map over a list of texts, returning its status, stdout and stderr."""

    status = main(("workflow", "run", str(MAP_WORKFLOW_ID), "--input", texts, "--output", "result"))
    captured = capsys.readouterr()

    return status, captured.out, captured.err


# The documents


@pytest.mark.parametrize("path", [CHILD_DOCUMENT, MAP_DOCUMENT], ids=lambda path: path.name)
def test_the_map_example_documents_are_canonical(
    path: Path,
) -> None:
    encoded = path.read_text(encoding="utf-8")

    assert encode_workflow_document(decode_workflow_document(encoded)) == encoded.rstrip("\n")


def test_the_map_example_requires_map_workflow_1_0_with_constant_settings() -> None:
    workflow = decode_workflow_document(MAP_DOCUMENT.read_text(encoding="utf-8"))
    (step,) = workflow.steps

    assert step.id == MAP_STEP_ID
    assert isinstance(step.specification, ToolStepSpecification)
    assert step.specification.requirement.name == "map_workflow"
    assert step.specification.requirement.version == "1.0.0"

    (settings,) = (binding for binding in step.inputs if binding.name == "settings")

    assert settings.source == WorkflowConstantValue(
        value={"workflow_id": str(CHILD_WORKFLOW_ID), "max_items": 100, "max_concurrency": 4}
    )


def test_the_child_selects_its_item_before_counting_it() -> None:
    workflow = decode_workflow_document(CHILD_DOCUMENT.read_text(encoding="utf-8"))

    names = []

    for step in workflow.steps:
        assert isinstance(step.specification, ToolStepSpecification)
        names.append(step.specification.requirement.name)

    assert names == ["json_select", "word_count_process"]
    assert workflow.result is not None
    assert workflow.result.name == "count"


# The walkthrough


def test_the_map_counts_every_text_in_list_order(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_map(capsys) == (0, f"{MAPPED}\n", "")


def test_every_text_is_its_own_invocation_listed_under_the_maps_run(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_map(capsys)

    repositories = open_repositories(walkthrough)
    (run,) = repositories.runs.runs_for_workflow(MAP_WORKFLOW_ID)

    assert len(repositories.invocations.invocations_for_workflow(CHILD_WORKFLOW_ID)) == 3

    status = main(("run", "children", str(run.id)))
    out = capsys.readouterr().out

    assert status == 0
    assert out.count("Status: succeeded\n") == 3
    assert out.count(f"Parent Step ID: {MAP_STEP_ID} (attempt 1)\n") == 3


def test_an_empty_list_maps_to_an_empty_list(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_map(capsys, "[]") == (0, "[]\n", "")


def test_a_list_beyond_max_items_is_refused_before_any_child_runs(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, err = run_map(capsys, json.dumps(["word"] * 101))

    assert (status, out) == (1, "")
    assert "Map of 101 items exceeds its max_items of 100." in err
    assert open_repositories(walkthrough).invocations.invocations() == ()


# The guides


@pytest.mark.parametrize("guide", GUIDES, ids=lambda path: path.name)
def test_the_guides_show_the_real_output(
    guide: Path,
) -> None:
    text = guide.read_text(encoding="utf-8")

    assert MAPPED in text
    assert "a1000000-0000-4000-8000-000000000007" in text
    assert f"--input '{TEXTS}'" in text
