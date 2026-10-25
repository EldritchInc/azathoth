"""Tests for executing tool implementations as subprocesses."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.tools import (
    PROCESS_STDERR_TAIL_CHARACTERS,
    PROCESS_TOOL_RUNTIME,
    ProcessToolExecutor,
    RuntimeToolExecutor,
    ToolExecutionError,
    ToolImplementation,
    UnsupportedToolRuntimeError,
    supported_tool_runtimes,
)

TOOL_ID = UUID("3d4e5f6a-7b8c-4d9e-9fa0-2b3c4d5e6f01")

IMPLEMENTATION_ID = UUID("3d4e5f6a-7b8c-4d9e-9fa0-2b3c4d5e6f11")

PYTHON_COMMAND = ("python3",)

BASH_COMMAND = ("bash",)

WORD_COUNT_SCRIPT = (
    "import json, sys\n"
    "inputs = json.load(sys.stdin)\n"
    "print(json.dumps({'count': len(inputs['text'].split())}))\n"
)

ENVIRONMENT_VARIABLE = "AZATHOTH_PROCESS_TOOL_TEST"


def create_implementation(
    source: str,
    *,
    command: tuple[str, ...] = PYTHON_COMMAND,
    timeout_seconds: float | None = None,
) -> ToolImplementation:
    """Create one process implementation running the given script."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source=source,
        command=command,
        timeout_seconds=timeout_seconds,
    )


def execute(
    implementation: ToolImplementation,
    inputs: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """Execute one process implementation."""

    return asyncio.run(
        ProcessToolExecutor().execute(
            implementation,
            inputs if inputs is not None else {},
        )
    )


def test_process_tool_reads_inputs_and_writes_outputs_as_json() -> None:
    assert execute(
        create_implementation(WORD_COUNT_SCRIPT),
        {
            "text": "one two three",
        },
    ) == {
        "count": 3,
    }


def test_bash_process_tool_receives_the_inputs_object() -> None:
    result = execute(
        create_implementation(
            'read -r inputs\nprintf \'{"received": %s}\' "$inputs"\n',
            command=BASH_COMMAND,
        ),
        {
            "text": "hello",
            "count": 2,
        },
    )

    assert result == {
        "received": {
            "text": "hello",
            "count": 2,
        },
    }


def test_process_tool_script_path_follows_the_command_arguments() -> None:
    result = execute(
        create_implementation(
            "unused",
            command=(
                "python3",
                "-c",
                "import json, sys; print(json.dumps({'arguments': sys.argv[1:]}))",
            ),
        ),
    )

    arguments = result["arguments"]

    assert isinstance(arguments, list)
    assert len(arguments) == 1

    script = arguments[0]

    assert isinstance(script, str)
    assert Path(script).name == "tool"


def test_process_tool_script_is_removed_after_execution() -> None:
    result = execute(
        create_implementation(
            "import json, sys\nprint(json.dumps({'script': sys.argv[0]}))\n",
        ),
    )

    script = result["script"]

    assert isinstance(script, str)
    assert not Path(script).exists()


def test_process_tool_inherits_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        "eldritch",
    )

    result = execute(
        create_implementation(
            "import json, os\n"
            f"print(json.dumps({{'value': os.environ['{ENVIRONMENT_VARIABLE}']}}))\n",
        ),
    )

    assert result == {
        "value": "eldritch",
    }


def test_process_tool_failure_reports_status_and_stderr() -> None:
    with pytest.raises(
        ToolExecutionError,
        match=f"^Tool implementation {IMPLEMENTATION_ID} exited with status 3: boom$",
    ):
        execute(
            create_implementation(
                "import sys\nprint('boom', file=sys.stderr)\nsys.exit(3)\n",
            ),
        )


def test_process_tool_failure_without_stderr_reports_status_only() -> None:
    with pytest.raises(
        ToolExecutionError,
        match=f"^Tool implementation {IMPLEMENTATION_ID} exited with status 4.$",
    ):
        execute(
            create_implementation(
                "import sys\nsys.exit(4)\n",
            ),
        )


def test_process_tool_failure_quotes_only_the_stderr_tail() -> None:
    with pytest.raises(ToolExecutionError) as raised:
        execute(
            create_implementation(
                "import sys\nsys.stderr.write('a' * 2000 + 'END')\nsys.exit(1)\n",
            ),
        )

    message = str(raised.value)
    prefix = f"Tool implementation {IMPLEMENTATION_ID} exited with status 1: "

    assert message.startswith(prefix)
    assert message.endswith("END")
    assert len(message) == len(prefix) + PROCESS_STDERR_TAIL_CHARACTERS


def test_process_tool_rejects_non_json_output() -> None:
    with pytest.raises(
        ToolExecutionError,
        match=f"^Tool implementation {IMPLEMENTATION_ID} produced invalid output.$",
    ):
        execute(
            create_implementation(
                "print('not json')\n",
            ),
        )


def test_process_tool_rejects_output_that_is_not_an_object() -> None:
    with pytest.raises(
        ToolExecutionError,
        match=f"^Tool implementation {IMPLEMENTATION_ID} produced invalid output.$",
    ):
        execute(
            create_implementation(
                "print('[1, 2, 3]')\n",
            ),
        )


def test_process_tool_reports_a_missing_command() -> None:
    with pytest.raises(
        ToolExecutionError,
        match=(
            f"^Tool implementation {IMPLEMENTATION_ID} command "
            "'azathoth-no-such-interpreter' was not found.$"
        ),
    ):
        execute(
            create_implementation(
                "unused",
                command=("azathoth-no-such-interpreter",),
            ),
        )


def test_process_tool_is_killed_when_it_times_out() -> None:
    with pytest.raises(
        ToolExecutionError,
        match=f"^Tool implementation {IMPLEMENTATION_ID} timed out after 0.2 seconds.$",
    ):
        execute(
            create_implementation(
                "import time\ntime.sleep(30)\n",
                timeout_seconds=0.2,
            ),
        )


def test_process_executor_rejects_other_runtimes() -> None:
    with pytest.raises(
        UnsupportedToolRuntimeError,
        match="^ProcessToolExecutor only supports the 'process' runtime.$",
    ):
        execute(
            ToolImplementation(
                tool_id=TOOL_ID,
                tool_version="1.0.0",
                runtime="python",
                source="def run():\n    return {}\n",
            ),
        )


def test_default_runtime_executor_runs_process_tools() -> None:
    result = asyncio.run(
        RuntimeToolExecutor().execute(
            create_implementation(WORD_COUNT_SCRIPT),
            {
                "text": "one two",
            },
        )
    )

    assert result == {
        "count": 2,
    }


def test_process_is_a_supported_tool_runtime() -> None:
    assert supported_tool_runtimes() == (
        "process",
        "python",
    )


def test_process_tool_output_is_decoded_as_json() -> None:
    result = execute(
        create_implementation(
            "import json\nprint(json.dumps({'nested': {'values': [1, 2.5, None, True]}}))\n",
        ),
    )

    assert result == {
        "nested": {
            "values": [
                1,
                2.5,
                None,
                True,
            ],
        },
    }
