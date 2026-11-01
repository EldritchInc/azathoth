"""Tests that the data-shaping tools speak UTF-8 whatever the platform's encoding.

On Windows a process's standard streams default to the locale's code page,
such as cp1252, and the base environment a process tool receives sets no
`PYTHONIOENCODING`. The engine decodes a tool's output and errors as UTF-8,
so each tool must write bytes, not text in the platform's encoding. These
tests force a legacy encoding so every platform checks what Windows sees.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import JsonValue

from tests.standard.harness import standard_implementation

LEGACY_ENCODINGS = ("cp1252", "ascii")

#
# One failure per tool whose message carries characters cp1252 cannot write
# as UTF-8: an ellipsis, accents, or characters cp1252 has no code for at all.
#
FAILURES: tuple[tuple[str, dict[str, JsonValue], int, str], ...] = (
    (
        "json_select",
        {"value": {}, "path": ["灯台"]},
        1,
        "json_select found no value at path [\"灯台\"]: missing object key '灯台'.",
    ),
    (
        "json_merge",
        {"base": {}, "patch": {}, "été": 1},
        2,
        "json_merge does not take the input 'été'.",
    ),
    (
        "validate_json",
        {"value": "a" * 400, "schema": {"type": "integer"}},
        1,
        "validate_json rejected the value at $: '" + "a" * 298 + "…",
    ),
    (
        "chunk_text",
        {"text": "x", "max_characters": 5, "größe": 1},
        2,
        "chunk_text does not take the input 'größe'.",
    ),
    (
        "join_text",
        {"items": [{}], "item_template": "{été}"},
        1,
        "join_text found no value for {été} in item $[0].",
    ),
    (
        "render_template",
        {"template": "{灯台}"},
        2,
        "render_template has no value for {灯台}.",
    ),
)


def run_with_encoding(
    tmp_path: Path,
    name: str,
    inputs: dict[str, JsonValue],
    encoding: str,
) -> subprocess.CompletedProcess[bytes]:
    """Run one standard tool's source with its standard streams in a legacy encoding."""

    script = tmp_path / f"{name}.py"
    script.write_text(standard_implementation(name).source, encoding="utf-8")

    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(inputs).encode("utf-8"),
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": encoding, "PYTHONUTF8": "0"},
        check=False,
    )


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
@pytest.mark.parametrize(
    ("name", "inputs", "status", "message"),
    [pytest.param(*failure, id=failure[0]) for failure in FAILURES],
)
def test_tool_errors_are_utf8_in_any_encoding(
    tmp_path: Path,
    name: str,
    inputs: dict[str, JsonValue],
    status: int,
    message: str,
    encoding: str,
) -> None:
    completed = run_with_encoding(tmp_path, name, inputs, encoding)

    assert completed.returncode == status
    assert completed.stderr.decode("utf-8") == message
    assert completed.stdout == b""


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_tool_output_is_utf8_in_any_encoding(
    tmp_path: Path,
    encoding: str,
) -> None:
    completed = run_with_encoding(
        tmp_path,
        "json_object",
        {"title": "Le phare — été", "place": "灯台"},
        encoding,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.decode("utf-8")) == {
        "value": {"title": "Le phare — été", "place": "灯台"}
    }


def test_every_failing_data_tool_is_covered() -> None:
    covered = {failure[0] for failure in FAILURES}

    assert covered == {
        "json_select",
        "json_merge",
        "validate_json",
        "chunk_text",
        "join_text",
        "render_template",
    }
