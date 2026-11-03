"""Tests for `map_workflow`: a child per item, several at a time, results in order (ADR 0106).

Each test deploys a small child workflow whose one step runs a probe tool.
The probe echoes its item, can sleep, fail, or record when it ran, so the
tests see order, concurrency and failures as real child processes produce
them.
"""

import json
import re
import time
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.cli import main
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from tests.examples.test_word_count_benchmark_examples import configure_walkthrough, run_cli
from tests.standard.harness import run_standard_tool, standard_document, standard_tool_failure

PROBE_TOOL_ID = "c1a00000-0000-4000-8000-000000000001"

CHILD_WORKFLOW_ID = "c1a00000-0000-4000-8000-000000000011"

PARENT_WORKFLOW_ID = "c1a00000-0000-4000-8000-000000000021"

MAP_STEP_ID = "c1a00000-0000-4000-8000-000000000031"

PROBE_SOURCE = (
    "import json\nimport sys\nimport time\nfrom pathlib import Path\n\n"
    "request = json.load(sys.stdin)['request']\n"
    "item = request['item']\n"
    "index = request['index']\n"
    "probe = item.get('probe')\n"
    "tally = item.get('tally')\n"
    "if tally:\n"
    "    with Path(tally, f'{index}.tally').open('a') as runs:\n"
    "        runs.write('ran\\n')\n"
    "if probe:\n"
    "    Path(probe, f'{index}.start').write_text(repr(time.time()))\n"
    "barrier = item.get('barrier')\n"
    "deadline = time.time() + 30\n"
    "def started():\n"
    "    return len(list(Path(probe).glob('*.start')))\n"
    "while barrier and started() < barrier and time.time() < deadline:\n"
    "    time.sleep(0.02)\n"
    "time.sleep(item.get('sleep', 0))\n"
    "if probe:\n"
    "    Path(probe, f'{index}.end').write_text(repr(time.time()))\n"
    "if item.get('fail'):\n"
    "    sys.stderr.write(f'item {index} refused')\n"
    "    sys.exit(1)\n"
    "json.dump({'echo': {'value': item.get('value'), 'index': index}}, sys.stdout)\n"
)
"""Echo the item and its index, after sleeping, failing or recording as the item asks.

A `tally` directory gets one line per execution of the item, so a test can
prove an item ran exactly once. With a `probe` directory and a `barrier`,
the item waits, for up to 30 seconds, until that many items have started,
so a test can prove that many ran at once however slowly processes start.
"""


def probe_tool() -> dict[str, object]:
    """Return the probe process tool."""

    return {
        "definition": {
            "id": PROBE_TOOL_ID,
            "name": "map_probe",
            "description": "Echo one mapped item.",
            "version": "1.0.0",
            "input_schema": {
                "json_schema": {
                    "type": "object",
                    "properties": {"request": {"type": "object"}},
                    "required": ["request"],
                }
            },
            "output_schema": {
                "json_schema": {
                    "type": "object",
                    "properties": {"echo": {"type": "object"}},
                    "required": ["echo"],
                }
            },
        },
        "implementations": [
            {
                "id": "c1a00000-0000-4000-8000-000000000002",
                "tool_id": PROBE_TOOL_ID,
                "tool_version": "1.0.0",
                "version": "1.0.0",
                "runtime": "process",
                "entrypoint": "run",
                "source": PROBE_SOURCE,
                "command": ["python"],
                "timeout_seconds": 60.0,
            }
        ],
        "test_cases": [],
    }


def step_document(
    step_id: str,
    requirement: dict[str, str],
    inputs: list[dict[str, object]],
    output: str,
) -> dict[str, object]:
    """Return one workflow step that runs a process tool and outputs one value."""

    return {
        "id": step_id,
        "specification": {"requirement": requirement},
        "depends_on": [],
        "inputs": inputs,
        "outputs": [{"name": output, "path": [output]}],
        "conditions": [],
        "retry_policy": {
            "max_attempts": 1,
            "initial_delay_seconds": 0.0,
            "backoff_multiplier": 1.0,
            "maximum_delay_seconds": None,
        },
        "failure_policy": "fail_workflow",
    }


WORKFLOW_INPUT = {"event_type": "workflow.input.received", "field_name": "input"}


def child_workflow() -> dict[str, object]:
    """Return the child: one probe step over the item it is given."""

    return {
        "metadata": {
            "id": CHILD_WORKFLOW_ID,
            "name": "probe one item",
            "description": "Echo one mapped item.",
            "version": "1.0.0",
        },
        "steps": [
            step_document(
                "c1a00000-0000-4000-8000-000000000012",
                {"name": "map_probe", "version": "1.0.0", "runtime": "process"},
                [{"name": "request", "source": WORKFLOW_INPUT}],
                "echo",
            )
        ],
        "result": {"name": "echo"},
    }


def parent_workflow(
    settings: dict[str, JsonValue],
) -> dict[str, object]:
    """Return a parent that maps the child over the list it is given."""

    return {
        "metadata": {
            "id": PARENT_WORKFLOW_ID,
            "name": "map the probe",
            "description": "Map the probe child over a list.",
            "version": "1.0.0",
        },
        "steps": [
            step_document(
                MAP_STEP_ID,
                {"name": "map_workflow", "version": "1.0.0", "runtime": "process"},
                [
                    {"name": "settings", "source": {"value": settings}},
                    {"name": "items", "source": WORKFLOW_INPUT},
                ],
                "results",
            )
        ],
        "result": {"name": "results"},
    }


def import_document(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    kind: str,
    document: dict[str, object],
) -> None:
    """Write one document and import it."""

    path = tmp_path / f"{kind}-{len(list(tmp_path.glob('*.json')))}.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    run_cli(capsys, kind, "import", str(path))


def deploy_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Deploy the probe child into a fresh database, with the standard tools, and return it."""

    path = configure_walkthrough(monkeypatch, tmp_path)

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)

    import_document(capsys, tmp_path, "tool", probe_tool())
    run_cli(capsys, "tool", "install-standard")
    import_document(capsys, tmp_path, "workflow", child_workflow())
    run_cli(capsys, "workflow", "promote", CHILD_WORKFLOW_ID)

    return path


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Return a fresh database with the probe child deployed."""

    return deploy_probe(monkeypatch, tmp_path, capsys)


def settings(
    **overrides: JsonValue,
) -> dict[str, JsonValue]:
    """Return map settings over the probe child, with overrides."""

    return {"workflow_id": CHILD_WORKFLOW_ID, "max_items": 20, **overrides}


def map_items(
    items: list[JsonValue],
    **overrides: JsonValue,
) -> dict[str, JsonValue]:
    """Run the map tool over the items, outside any step, and return its output."""

    return run_standard_tool("map_workflow", {"settings": settings(**overrides), "items": items})


def echoed(
    *values: JsonValue,
) -> list[JsonValue]:
    """Return what the probe child emits for each value, in order."""

    return [{"result": {"value": value, "index": index}} for index, value in enumerate(values)]


def invocation_count(
    database: Path,
) -> int:
    """Return how many child invocations the database records."""

    return len(open_repositories(database).invocations.invocations())


# Results


def test_results_come_back_in_item_order_whatever_order_children_finish_in(
    database: Path,
) -> None:
    output = map_items(
        [
            {"value": "slowest", "sleep": 0.8},
            {"value": "fastest"},
            {"value": "middle", "sleep": 0.4},
        ]
    )

    assert output == {"results": echoed("slowest", "fastest", "middle"), "count": 3}


def test_each_child_receives_its_item_and_its_index(
    database: Path,
) -> None:
    map_items([{"value": "a"}, {"value": "b"}])

    inputs = sorted(
        (
            invocation.initial_context.by_type("workflow.input.received")[0].payload["input"]
            for invocation in open_repositories(database).invocations.invocations()
        ),
        key=lambda value: json.dumps(value),
    )

    assert inputs == [
        {"item": {"value": "a"}, "index": 0},
        {"item": {"value": "b"}, "index": 1},
    ]


def test_an_empty_list_invokes_nothing(
    database: Path,
) -> None:
    assert map_items([]) == {"results": [], "count": 0}
    assert invocation_count(database) == 0


# Concurrency


def overlap(
    probe: Path,
    count: int,
) -> int:
    """Return the most children the probe saw running at the same moment."""

    spans = [
        (float((probe / f"{index}.start").read_text()), float((probe / f"{index}.end").read_text()))
        for index in range(count)
    ]

    return max(sum(1 for start, end in spans if start <= moment < end) for moment, _ in spans)


@pytest.mark.parametrize("concurrency", [1, 2, 3])
def test_no_more_than_max_concurrency_children_run_at_once(
    database: Path,
    tmp_path: Path,
    concurrency: int,
) -> None:
    probe = tmp_path / f"probe-{concurrency}"
    probe.mkdir()

    #
    # Each item waits until `concurrency` items have started, so they run
    # together however slowly the platform starts processes; a map that
    # ran fewer at once would leave them waiting out the barrier's timeout,
    # and one that ran more would overlap more.
    #
    output = map_items(
        [
            {"value": index, "sleep": 0.2, "probe": str(probe), "barrier": concurrency}
            for index in range(6)
        ],
        max_concurrency=concurrency,
    )

    assert output["count"] == 6
    assert overlap(probe, 6) == concurrency


def test_eight_children_write_to_one_sqlite_file_at_once(
    database: Path,
) -> None:
    output = map_items([{"value": index} for index in range(8)], max_concurrency=8)

    assert output == {"results": echoed(*range(8)), "count": 8}
    assert invocation_count(database) == 8


# Failures


def test_every_item_runs_and_the_first_failure_is_named_with_how_many_failed(
    database: Path,
) -> None:
    items: list[JsonValue] = [{"value": index, "fail": index in (1, 3)} for index in range(5)]

    status, message = standard_tool_failure(
        "map_workflow", {"settings": settings(), "items": items}
    )

    assert status == 1
    assert re.fullmatch(
        rf"Item 1 of 5: child workflow {CHILD_WORKFLOW_ID} invocation [0-9a-f-]{{36}} failed: "
        r"Production workflow execution failed\. \(2 of 5 items failed\)\.",
        message,
    ), message
    assert invocation_count(database) == 5


def test_a_child_that_outlasts_its_timeout_fails_its_item(
    database: Path,
) -> None:
    status, message = standard_tool_failure(
        "map_workflow",
        {"settings": settings(child_timeout_seconds=1), "items": [{"value": 0, "sleep": 5}]},
    )

    assert (status, message) == (
        1,
        f"Item 0 of 1: child workflow {CHILD_WORKFLOW_ID} timed out after 1 seconds. "
        "(1 of 1 items failed).",
    )


def test_a_map_that_runs_out_of_budget_leaves_its_children_to_finish(
    database: Path,
) -> None:
    status, message = standard_tool_failure(
        "map_workflow",
        {
            "settings": settings(budget_seconds=1),
            "items": [{"value": 0, "sleep": 3}, {"value": 1, "sleep": 3}],
        },
    )

    assert (status, message) == (
        1,
        f"Map over child workflow {CHILD_WORKFLOW_ID} ran out of time after 0 of 2 items finished.",
    )

    #
    # Both children were already running, and finish under their own runs.
    #
    repositories = open_repositories(database)
    deadline = time.monotonic() + 30

    while True:
        invocations = repositories.invocations.invocations()
        results = [repositories.invocations.result(invocation.id) for invocation in invocations]

        if len(invocations) == 2 and all(result is not None for result in results):
            break

        assert time.monotonic() < deadline, "the children never finished"
        time.sleep(0.1)


# Settings


@pytest.mark.parametrize(
    ("overrides", "items", "message"),
    [
        pytest.param(
            {"workflow_id": ""},
            [],
            "Map settings must name the child workflow_id.",
            id="no-workflow",
        ),
        pytest.param(
            {"max_items": 0},
            [],
            "Map settings must set max_items to a positive integer.",
            id="zero-items",
        ),
        pytest.param(
            {"max_items": True},
            [],
            "Map settings must set max_items to a positive integer.",
            id="boolean-items",
        ),
        pytest.param(
            {"max_concurrency": 0},
            [],
            "Map settings must set max_concurrency to an integer from 1 to 16.",
            id="no-concurrency",
        ),
        pytest.param(
            {"max_concurrency": 17},
            [],
            "Map settings must set max_concurrency to an integer from 1 to 16.",
            id="too-concurrent",
        ),
        pytest.param(
            {"child_timeout_seconds": 0},
            [],
            "Map settings must set child_timeout_seconds to a positive number.",
            id="no-timeout",
        ),
        pytest.param(
            {"budget_seconds": 0},
            [],
            "Map settings must set budget_seconds to a positive number.",
            id="no-budget",
        ),
        pytest.param(
            {"budget_seconds": 86400},
            [],
            "Map budget of 86400 seconds exceeds the tool's timeout of 86400 seconds "
            "less a 60-second margin.",
            id="budget-beyond-timeout",
        ),
        pytest.param(
            {"max_items": 2},
            [{"value": 0}, {"value": 1}, {"value": 2}],
            "Map of 3 items exceeds its max_items of 2.",
            id="too-many-items",
        ),
    ],
)
def test_settings_that_cannot_be_used_are_refused_before_any_child_runs(
    database: Path,
    overrides: dict[str, JsonValue],
    items: list[JsonValue],
    message: str,
) -> None:
    status, detail = standard_tool_failure(
        "map_workflow", {"settings": settings(**overrides), "items": items}
    )

    assert (status, detail) == (1, message)
    assert invocation_count(database) == 0


# Inside a workflow


def test_a_mapping_step_invokes_each_item_under_its_own_key(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import_document(capsys, tmp_path, "workflow", parent_workflow(settings(max_concurrency=2)))

    status = main(
        (
            "workflow",
            "run",
            PARENT_WORKFLOW_ID,
            "--input",
            json.dumps([{"value": "a"}, {"value": "b"}, {"value": "c"}]),
            "--output",
            "result",
        )
    )
    captured = capsys.readouterr()

    assert (status, json.loads(captured.out)) == (0, echoed("a", "b", "c"))

    repositories = open_repositories(database)
    (parent,) = repositories.runs.runs_for_workflow(UUID(PARENT_WORKFLOW_ID))

    keys = sorted(
        invocation.idempotency.key
        for invocation in repositories.invocations.invocations()
        if invocation.idempotency is not None
    )

    assert keys == [f"azathoth:{parent.id}:{MAP_STEP_ID}:1:{index}" for index in range(3)]
    assert len(repositories.run_children.children_of(parent.id)) == 3


def test_outside_a_step_the_children_have_no_key(
    database: Path,
) -> None:
    map_items([{"value": "a"}])

    (invocation,) = open_repositories(database).invocations.invocations()

    assert invocation.idempotency is None


# Documentation

STANDARD_README = Path(__file__).parents[2] / "src" / "azathoth" / "standard" / "README.md"


def test_the_readme_quotes_the_real_refusals_and_failures() -> None:
    text = STANDARD_README.read_text(encoding="utf-8")
    section = text[text.index("### map_workflow") : text.index("## The Data-Shaping Tools")]

    for line in (
        "Map settings must name the child workflow_id.",
        "Map settings must set max_items to a positive integer.",
        "Map settings must set max_concurrency to an integer from 1 to 16.",
        "Map settings must set child_timeout_seconds to a positive number.",
        "Map settings must set budget_seconds to a positive number.",
        "Map budget of <SECONDS> seconds exceeds the tool's timeout of <TIMEOUT> seconds "
        "less a 60-second margin.",
        "Map of <COUNT> items exceeds its max_items of <MAX_ITEMS>.",
        "Map over child workflow <WORKFLOW_ID> ran out of time after <FINISHED> of <COUNT> "
        "items finished.",
        "Item <INDEX> of <COUNT>: child workflow <WORKFLOW_ID> invocation <INVOCATION_ID> "
        "failed: <MESSAGE> (<FAILED> of <COUNT> items failed).",
        "Item <INDEX> of <COUNT>: child workflow <WORKFLOW_ID> timed out after <SECONDS> "
        "seconds. (<FAILED> of <COUNT> items failed).",
    ):
        assert f"\n{line}\n" in section, line


def test_the_readme_lists_the_map_settings_the_tool_reads() -> None:
    text = STANDARD_README.read_text(encoding="utf-8")
    section = text[text.index("### map_workflow") : text.index("## The Data-Shaping Tools")]
    documented = [line.split("`")[1] for line in section.splitlines() if line.startswith("| `")]
    schema = json.loads(
        json.dumps(standard_document("map_workflow").definition.input_schema.json_schema)
    )
    settings_schema = schema["properties"]["settings"]

    assert isinstance(settings_schema, dict)
    assert documented == list(settings_schema["properties"])
    assert settings_schema["required"] == ["workflow_id", "max_items"]
