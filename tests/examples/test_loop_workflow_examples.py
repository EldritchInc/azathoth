"""Tests proving the loop-workflow tool example and its countdown walkthrough."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.cli import main
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    SQLiteWorkflowRunRepository,
    ToolStepSpecification,
    WorkflowNamedValueReference,
    decode_workflow_document,
    encode_workflow_document,
)
from tests.examples.test_word_count_benchmark_examples import (
    configure_walkthrough,
    run_cli,
)

PROJECT_ROOT = Path(__file__).parents[2]

TOOL_EXAMPLES = PROJECT_ROOT / "examples" / "tools"

WORKFLOW_EXAMPLES = PROJECT_ROOT / "examples" / "workflows"

LOOP_TOOL_DOCUMENT = TOOL_EXAMPLES / "loop-workflow.json"

COUNTDOWN_TOOL_DOCUMENT = TOOL_EXAMPLES / "countdown-step.json"

COUNTDOWN_WORKFLOW_DOCUMENT = WORKFLOW_EXAMPLES / "countdown.json"

LOOP_WORKFLOW_DOCUMENT = WORKFLOW_EXAMPLES / "loop-countdown.json"

LOOP_IMPLEMENTATION_ID = UUID("c1000000-0000-4000-8000-000000000012")

COUNTDOWN_WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000004")

LOOP_WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000005")

SEVEN_WORKFLOW_ID = UUID("d1000000-0000-4000-8000-000000000001")

DEPTH_VARIABLE = "AZATHOTH_WORKFLOW_DEPTH"

TOOL_FAILURE_PREFIX = f"Tool implementation {LOOP_IMPLEMENTATION_ID} exited with status"

DOCUMENTS = (
    LOOP_TOOL_DOCUMENT,
    COUNTDOWN_TOOL_DOCUMENT,
    COUNTDOWN_WORKFLOW_DOCUMENT,
    LOOP_WORKFLOW_DOCUMENT,
)


def loop_settings(
    workflow_id: UUID = COUNTDOWN_WORKFLOW_ID,
    *,
    max_iterations: int = 10,
    remaining: int = 3,
    budget_seconds: JsonValue = None,
) -> str:
    """Return the parent's JSON input naming the child, the limit and the starting state.

    A budget is included only when one is given.
    """

    settings: dict[str, JsonValue] = {
        "workflow_id": str(workflow_id),
        "max_iterations": max_iterations,
        "state": {"remaining": remaining},
    }

    if budget_seconds is not None:
        settings["budget_seconds"] = budget_seconds

    return json.dumps(settings)


def import_loop_tool_with_timeout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    timeout_seconds: float,
) -> None:
    """Import a revision of the loop tool that declares a shorter timeout."""

    document = json.loads(LOOP_TOOL_DOCUMENT.read_text(encoding="utf-8"))
    document["implementations"][0]["timeout_seconds"] = timeout_seconds

    revision = tmp_path / "loop-workflow-short.json"
    revision.write_text(json.dumps(document), encoding="utf-8")

    run_cli(capsys, "tool", "import", str(revision))


def configure_loop_walkthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    promote_child: bool = True,
) -> Path:
    """Import the loop examples into an isolated database and return it.

    Children run as real subprocesses that cannot see this process's
    monkeypatches, so the provider key and any inherited depth are removed
    from the environment they inherit.
    """

    database = configure_walkthrough(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(DEPTH_VARIABLE, raising=False)

    run_cli(capsys, "tool", "import", str(COUNTDOWN_TOOL_DOCUMENT))
    run_cli(capsys, "tool", "import", str(LOOP_TOOL_DOCUMENT))
    run_cli(capsys, "workflow", "import", str(COUNTDOWN_WORKFLOW_DOCUMENT))
    run_cli(capsys, "workflow", "import", str(LOOP_WORKFLOW_DOCUMENT))

    if promote_child:
        run_cli(capsys, "workflow", "promote", str(COUNTDOWN_WORKFLOW_ID))

    return database


def run_loop(
    capsys: pytest.CaptureFixture[str],
    settings: str,
) -> tuple[int, str, str]:
    """Run the loop workflow for its result, returning status, stdout and stderr."""

    status = main(
        (
            "workflow",
            "run",
            str(LOOP_WORKFLOW_ID),
            "--input",
            settings,
            "--output",
            "result",
        )
    )

    captured = capsys.readouterr()

    output: str = captured.out
    errors: str = captured.err

    return status, output, errors


def loop_values(
    database: Path,
) -> dict[str, object]:
    """Return the values the loop step recorded in the latest loop run."""

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(LOOP_WORKFLOW_ID)

    assert runs

    return {value.name: value.value for value in runs[-1].steps[0].values}


def import_seven_child(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Import and promote a child that returns a bare number instead of loop state."""

    tool = tmp_path / "seven-tool.json"
    workflow = tmp_path / "seven-workflow.json"

    tool.write_text(
        json.dumps(
            {
                "definition": {
                    "id": "d1000000-0000-4000-8000-000000000002",
                    "name": "seven",
                    "description": "Return seven.",
                    "version": "1.0.0",
                    "input_schema": {"json_schema": {"type": "object"}},
                    "output_schema": {"json_schema": {"type": "object"}},
                },
                "implementations": [
                    {
                        "id": "d1000000-0000-4000-8000-000000000003",
                        "tool_id": "d1000000-0000-4000-8000-000000000002",
                        "tool_version": "1.0.0",
                        "version": "1.0.0",
                        "runtime": "python",
                        "entrypoint": "run",
                        "source": "def run(request):\n    return {'value': 7}\n",
                    }
                ],
                "test_cases": [],
            }
        ),
        encoding="utf-8",
    )

    workflow.write_text(
        json.dumps(
            {
                "metadata": {
                    "id": str(SEVEN_WORKFLOW_ID),
                    "name": "seven",
                    "description": "A child that ignores the loop protocol.",
                    "version": "1.0.0",
                },
                "steps": [
                    {
                        "id": "d1000000-0000-4000-8000-000000000011",
                        "specification": {
                            "requirement": {
                                "name": "seven",
                                "version": "1.0.0",
                                "runtime": "python",
                            }
                        },
                        "inputs": [
                            {
                                "name": "request",
                                "source": {
                                    "event_type": "workflow.input.received",
                                    "field_name": "input",
                                },
                            }
                        ],
                        "outputs": [{"name": "value", "path": ["value"]}],
                    }
                ],
                "result": {"name": "value"},
            }
        ),
        encoding="utf-8",
    )

    run_cli(capsys, "tool", "import", str(tool))
    run_cli(capsys, "workflow", "import", str(workflow))
    run_cli(capsys, "workflow", "promote", str(SEVEN_WORKFLOW_ID))


@pytest.mark.parametrize(
    "document",
    [pytest.param(path, id=path.name) for path in DOCUMENTS],
)
def test_loop_example_documents_are_canonical(
    document: Path,
) -> None:
    encoded = document.read_text(encoding="utf-8")

    if document.parent == TOOL_EXAMPLES:
        assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")
    else:
        assert encode_workflow_document(decode_workflow_document(encoded)) == encoded.rstrip("\n")


def test_loop_tool_example_runs_python_as_a_long_lived_process() -> None:
    document = decode_tool_document(LOOP_TOOL_DOCUMENT.read_text(encoding="utf-8"))

    assert document.definition.name == "loop_workflow"

    implementation = document.implementations[0]

    assert implementation.id == LOOP_IMPLEMENTATION_ID
    assert implementation.runtime == PROCESS_TOOL_RUNTIME
    assert implementation.command == ("python",)
    assert implementation.timeout_seconds == 86400.0


def test_loop_tool_example_is_version_1_1() -> None:
    document = decode_tool_document(LOOP_TOOL_DOCUMENT.read_text(encoding="utf-8"))

    assert document.definition.version == "1.1.0"
    assert document.implementations[0].tool_version == "1.1.0"
    assert document.implementations[0].version == "1.1.0"


def test_loop_workflow_example_requires_loop_tool_1_1() -> None:
    workflow = decode_workflow_document(LOOP_WORKFLOW_DOCUMENT.read_text(encoding="utf-8"))

    requirement = workflow.steps[0].specification

    assert isinstance(requirement, ToolStepSpecification)
    assert requirement.requirement.name == "loop_workflow"
    assert requirement.requirement.version == "1.1.0"


def test_loop_workflow_example_returns_the_collected_items() -> None:
    workflow = decode_workflow_document(LOOP_WORKFLOW_DOCUMENT.read_text(encoding="utf-8"))

    assert workflow.metadata.id == LOOP_WORKFLOW_ID
    assert isinstance(workflow.result, WorkflowNamedValueReference)
    assert workflow.result.name == "items"


def test_loop_runs_the_child_until_it_is_done(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    status, output, errors = run_loop(capsys, loop_settings())

    assert (status, output, errors) == (0, "[3, 2, 1]\n", "")
    assert loop_values(database) == {
        "items": [3, 2, 1],
        "iterations": 3,
        "completed": True,
    }


def test_loop_stops_at_its_iteration_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    status, output, errors = run_loop(capsys, loop_settings(max_iterations=2))

    assert (status, output, errors) == (0, "[3, 2]\n", "")
    assert loop_values(database) == {
        "items": [3, 2],
        "iterations": 2,
        "completed": False,
    }


def test_loop_reports_the_failing_iteration_and_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys, promote_child=False)

    status, output, errors = run_loop(capsys, loop_settings())

    assert (status, output) == (1, "")
    assert (
        f"{TOOL_FAILURE_PREFIX} 1: Iteration 1: child workflow {COUNTDOWN_WORKFLOW_ID} invocation "
    ) in errors
    assert " failed: The requested workflow is not deployed to production." in errors


def test_loop_rejects_a_child_that_ignores_the_loop_protocol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys)
    import_seven_child(tmp_path, capsys)

    status, output, errors = run_loop(capsys, loop_settings(SEVEN_WORKFLOW_ID))

    assert (status, output) == (1, "")
    assert (
        f"{TOOL_FAILURE_PREFIX} 1: Iteration 1: child workflow {SEVEN_WORKFLOW_ID} must return "
        "an object with a boolean 'done', got 7."
    ) in errors


def test_loop_rejects_settings_without_a_positive_iteration_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    status, output, errors = run_loop(capsys, loop_settings(max_iterations=0))

    assert (status, output) == (1, "")
    assert (
        f"{TOOL_FAILURE_PREFIX} 1: Loop settings must set max_iterations to a positive integer."
    ) in errors


def test_loop_refuses_beyond_the_depth_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    monkeypatch.setenv(DEPTH_VARIABLE, "8")

    status, output, errors = run_loop(capsys, loop_settings())

    assert (status, output) == (1, "")
    assert f"{TOOL_FAILURE_PREFIX} 2: Child workflow depth 9 exceeds the limit of 8." in errors


def test_loop_runs_within_an_explicit_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    status, output, errors = run_loop(capsys, loop_settings(budget_seconds=600))

    assert (status, output, errors) == (0, "[3, 2, 1]\n", "")


@pytest.mark.parametrize(
    "budget",
    [
        pytest.param(0, id="zero"),
        pytest.param(-5, id="negative"),
        pytest.param(True, id="boolean"),
        pytest.param("600", id="string"),
    ],
)
def test_loop_rejects_a_budget_that_is_not_a_positive_number(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    budget: JsonValue,
) -> None:
    database = configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    status, output, errors = run_loop(capsys, loop_settings(budget_seconds=budget))

    assert (status, output) == (1, "")
    assert (
        f"{TOOL_FAILURE_PREFIX} 1: Loop settings must set budget_seconds to a positive number."
    ) in errors
    assert SQLiteWorkflowRunRepository(database).runs_for_workflow(COUNTDOWN_WORKFLOW_ID) == ()


def test_loop_rejects_a_budget_beyond_its_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    status, output, errors = run_loop(capsys, loop_settings(budget_seconds=86341))

    assert (status, output) == (1, "")
    assert (
        f"{TOOL_FAILURE_PREFIX} 1: Loop budget of 86341 seconds exceeds the tool's timeout "
        "of 86400 seconds less a 60-second margin."
    ) in errors


def test_loop_budget_is_bounded_by_the_timeout_it_is_given(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys)
    import_loop_tool_with_timeout(tmp_path, capsys, 120)

    status, output, errors = run_loop(capsys, loop_settings(budget_seconds=61))

    assert (status, output) == (1, "")
    assert (
        f"{TOOL_FAILURE_PREFIX} 1: Loop budget of 61 seconds exceeds the tool's timeout "
        "of 120 seconds less a 60-second margin."
    ) in errors


def test_loop_default_budget_fits_a_shorter_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_loop_walkthrough(monkeypatch, tmp_path, capsys)
    import_loop_tool_with_timeout(tmp_path, capsys, 120)

    status, output, errors = run_loop(capsys, loop_settings())

    assert (status, output, errors) == (0, "[3, 2, 1]\n", "")
