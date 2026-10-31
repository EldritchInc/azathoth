"""Tests proving the run-workflow tool example and its child-workflow walkthrough."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    ToolDocument,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    WorkflowFailurePolicy,
    WorkflowNamedValueReference,
    WorkflowSpecification,
    decode_workflow_document,
    encode_workflow_document,
)
from tests.examples.test_redundant_word_count_examples import (
    PROCESS_TOOL_DOCUMENT,
    PYTHON_TOOL_DOCUMENT,
)
from tests.examples.test_word_count_benchmark_examples import (
    DASHED_TEXT,
    configure_walkthrough,
    run_cli,
)
from tests.examples.test_word_count_messages_examples import (
    WORKFLOW_DOCUMENT as CHILD_WORKFLOW_DOCUMENT,
)
from tests.examples.test_word_count_messages_examples import (
    WORKFLOW_ID as CHILD_WORKFLOW_ID,
)

PROJECT_ROOT = Path(__file__).parents[2]

STANDARD_TOOLS = PROJECT_ROOT / "src" / "azathoth" / "standard" / "tools"

RUN_WORKFLOW_TOOL_DOCUMENT = STANDARD_TOOLS / "run-workflow.json"

PARENT_WORKFLOW_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "count-words-in-child.json"

RUN_WORKFLOW_TOOL_ID = UUID("c1000000-0000-4000-8000-000000000001")

RUN_WORKFLOW_IMPLEMENTATION_ID = UUID("c1000000-0000-4000-8000-000000000011")

PARENT_WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000003")

DEPTH_VARIABLE = "AZATHOTH_WORKFLOW_DEPTH"

TOOL_FAILURE_PREFIX = f"Tool implementation {RUN_WORKFLOW_IMPLEMENTATION_ID} exited with status"


def read_tool_document(
    path: Path,
) -> ToolDocument:
    """Decode one checked-in tool document."""

    return decode_tool_document(
        path.read_text(
            encoding="utf-8",
        )
    )


def read_parent_workflow() -> WorkflowSpecification:
    """Decode the checked-in parent workflow."""

    return decode_workflow_document(
        PARENT_WORKFLOW_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )


def child_call(
    workflow_id: UUID,
    workflow_input: object,
) -> str:
    """Return the parent's JSON input naming one child workflow and its input."""

    return json.dumps(
        {
            "workflow_id": str(workflow_id),
            "input": workflow_input,
        }
    )


def configure_child_walkthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Import every walkthrough document into an isolated database.

    The child runs as a real subprocess that cannot see this process's
    monkeypatches, so the provider key and any inherited depth are removed
    from the environment it inherits.
    """

    configure_walkthrough(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.delenv(
        "OPENROUTER_API_KEY",
        raising=False,
    )

    monkeypatch.delenv(
        DEPTH_VARIABLE,
        raising=False,
    )

    run_cli(capsys, "tool", "import", str(PYTHON_TOOL_DOCUMENT))
    run_cli(capsys, "tool", "import", str(PROCESS_TOOL_DOCUMENT))
    run_cli(capsys, "tool", "import", str(RUN_WORKFLOW_TOOL_DOCUMENT))
    run_cli(capsys, "workflow", "import", str(CHILD_WORKFLOW_DOCUMENT))
    run_cli(capsys, "workflow", "import", str(PARENT_WORKFLOW_DOCUMENT))


def run_parent(
    capsys: pytest.CaptureFixture[str],
    parent_input: str,
) -> tuple[int, str, str]:
    """Run the parent workflow for its result, returning status, stdout and stderr."""

    status = main(
        (
            "workflow",
            "run",
            str(PARENT_WORKFLOW_ID),
            "--input",
            parent_input,
            "--output",
            "result",
        )
    )

    captured = capsys.readouterr()

    output: str = captured.out
    errors: str = captured.err

    return status, output, errors


def test_run_workflow_tool_example_is_canonical() -> None:
    encoded = RUN_WORKFLOW_TOOL_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")


def test_run_workflow_tool_example_runs_python_as_a_process() -> None:
    document = read_tool_document(RUN_WORKFLOW_TOOL_DOCUMENT)

    assert document.definition.id == RUN_WORKFLOW_TOOL_ID
    assert document.definition.name == "run_workflow"
    assert document.test_cases == ()

    implementation = document.implementations[0]

    assert implementation.id == RUN_WORKFLOW_IMPLEMENTATION_ID
    assert implementation.runtime == PROCESS_TOOL_RUNTIME
    assert implementation.command == ("python",)
    assert implementation.timeout_seconds == 60.0


def test_count_words_in_child_example_is_canonical() -> None:
    encoded = PARENT_WORKFLOW_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encode_workflow_document(read_parent_workflow()) == encoded.rstrip("\n")


def test_count_words_in_child_example_halts_when_its_child_fails() -> None:
    workflow = read_parent_workflow()

    assert workflow.metadata.id == PARENT_WORKFLOW_ID
    assert len(workflow.steps) == 1

    step = workflow.steps[0]

    assert step.failure_policy == WorkflowFailurePolicy.FAIL_WORKFLOW
    assert step.message == "Invoking the child workflow"
    assert isinstance(workflow.result, WorkflowNamedValueReference)
    assert workflow.result.name == "count"


def test_child_workflow_walkthrough_counts_words_through_a_deployed_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_child_walkthrough(monkeypatch, tmp_path, capsys)

    run_cli(capsys, "workflow", "promote", str(CHILD_WORKFLOW_ID))

    status, output, errors = run_parent(
        capsys,
        child_call(CHILD_WORKFLOW_ID, DASHED_TEXT),
    )

    assert (status, errors) == (0, "")
    assert output == "7\n"


def test_child_workflow_walkthrough_reports_an_undeployed_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_child_walkthrough(monkeypatch, tmp_path, capsys)

    status, output, errors = run_parent(
        capsys,
        child_call(CHILD_WORKFLOW_ID, DASHED_TEXT),
    )

    assert status == 1
    assert output == ""
    assert f"{TOOL_FAILURE_PREFIX} 1: Child workflow {CHILD_WORKFLOW_ID} invocation " in errors
    assert " failed: The requested workflow is not deployed to production." in errors


def test_run_workflow_tool_refuses_beyond_the_depth_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_child_walkthrough(monkeypatch, tmp_path, capsys)

    run_cli(capsys, "workflow", "promote", str(CHILD_WORKFLOW_ID))

    monkeypatch.setenv(DEPTH_VARIABLE, "8")

    status, output, errors = run_parent(
        capsys,
        child_call(CHILD_WORKFLOW_ID, DASHED_TEXT),
    )

    assert status == 1
    assert output == ""
    assert f"{TOOL_FAILURE_PREFIX} 2: Child workflow depth 9 exceeds the limit of 8." in errors


@pytest.mark.parametrize(
    ("starting_depth", "succeeds"),
    [
        pytest.param(6, True, id="grandchild-at-the-limit"),
        pytest.param(7, False, id="grandchild-beyond-the-limit"),
    ],
)
def test_run_workflow_tool_passes_its_depth_to_the_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    starting_depth: int,
    succeeds: bool,
) -> None:
    configure_child_walkthrough(monkeypatch, tmp_path, capsys)

    run_cli(capsys, "workflow", "promote", str(CHILD_WORKFLOW_ID))
    run_cli(capsys, "workflow", "promote", str(PARENT_WORKFLOW_ID))

    monkeypatch.setenv(DEPTH_VARIABLE, str(starting_depth))

    status, output, errors = run_parent(
        capsys,
        child_call(
            PARENT_WORKFLOW_ID,
            {
                "workflow_id": str(CHILD_WORKFLOW_ID),
                "input": "two words",
            },
        ),
    )

    if succeeds:
        assert (status, output, errors) == (0, "2\n", "")
    else:
        assert status == 1
        assert output == ""
        assert f"Child workflow {PARENT_WORKFLOW_ID} invocation " in errors
        assert " failed: Production workflow execution failed." in errors
