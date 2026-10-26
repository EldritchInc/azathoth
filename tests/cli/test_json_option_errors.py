"""Tests for invalid JSON command-line values."""

from argparse import ArgumentTypeError
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.cli.parsing.common import json_value

WORKFLOW_ID = UUID("a1000000-0000-0000-0000-000000000002")

RUN_ID = UUID("c1000000-0000-0000-0000-000000000001")

BENCHMARK_ID = UUID("b1000000-0000-0000-0000-000000000001")

INVALID_JSON = "{not json"

DECODER_MESSAGE = "Expecting property name enclosed in double quotes"


def test_json_value_parses_any_json_value() -> None:
    assert json_value('"text"') == "text"
    assert json_value("6") == 6
    assert json_value("null") is None
    assert json_value('{"count": 2}') == {"count": 2}


def test_json_value_error_names_no_particular_option() -> None:
    with pytest.raises(ArgumentTypeError) as raised:
        json_value(INVALID_JSON)

    assert str(raised.value) == f"Value must be valid JSON: {DECODER_MESSAGE}"


@pytest.mark.parametrize(
    ("arguments", "option"),
    [
        pytest.param(
            ("workflow", "run", str(WORKFLOW_ID), "--input", INVALID_JSON),
            "--input",
            id="workflow-run-input",
        ),
        pytest.param(
            ("workflow", "invoke", str(WORKFLOW_ID), "--input", INVALID_JSON),
            "--input",
            id="workflow-invoke-input",
        ),
        pytest.param(
            (
                "run",
                "feedback",
                str(RUN_ID),
                "--bad",
                "--reason",
                "Wrong.",
                "--corrected-output",
                INVALID_JSON,
            ),
            "--corrected-output",
            id="run-feedback-corrected-output",
        ),
        pytest.param(
            (
                "benchmark",
                "add-case",
                str(BENCHMARK_ID),
                "--from-run",
                str(RUN_ID),
                "--comparison",
                "exact",
                "--expected",
                INVALID_JSON,
            ),
            "--expected",
            id="benchmark-add-case-expected",
        ),
    ],
)
def test_cli_invalid_json_names_the_option(
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
    option: str,
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert f"argument {option}: Value must be valid JSON: {DECODER_MESSAGE}" in captured.err
    assert "Expected value" not in captured.err
