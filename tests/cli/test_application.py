"""Tests for the Azathoth command-line application."""

import json
from argparse import ArgumentTypeError
from collections.abc import Sequence
from typing import cast
from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.application as application
from azathoth import __version__
from azathoth.cli import (
    build_parser,
    main,
)

FIRST_IDENTIFIER = "openrouter/example/model"

WORKFLOW_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _json_value(
    value: str,
) -> JsonValue:
    """Parse one JSON-compatible command-line value."""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ArgumentTypeError(f"expected value must be valid JSON: {exc.msg}") from exc

    return cast(
        JsonValue,
        parsed,
    )


def test_cli_parser_uses_azathoth_program_name() -> None:
    parser = build_parser()

    assert parser.prog == "azathoth"


def test_cli_parser_describes_azathoth() -> None:
    parser = build_parser()

    assert parser.description == ("Empirical optimization for context-aware AI workflows.")


def test_cli_without_arguments_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(())

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out.startswith("usage: azathoth")

    assert "Empirical optimization for context-aware AI workflows." in captured.out


def test_cli_help_exits_successfully(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert captured.out.startswith("usage: azathoth")

    assert "--version" in captured.out


def test_cli_version_exits_successfully(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--version",))

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert captured.out == (f"azathoth {__version__}\n")


def test_cli_rejects_unknown_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--definitely-not-an-option",))

    captured = capsys.readouterr()

    assert raised.value.code == 2

    assert captured.out == ""

    assert "usage: azathoth" in captured.err

    assert "unrecognized arguments: --definitely-not-an-option" in captured.err


@pytest.mark.parametrize(
    "argv",
    [
        (),
        [],
    ],
)
def test_cli_accepts_sequence_arguments(
    argv: Sequence[str],
) -> None:
    assert main(argv) == 0


def test_cli_model_help_exits_successfully(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "model",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "list" in captured.out
    assert "show" in captured.out


def test_cli_dispatches_model_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_list_models() -> int:
        nonlocal called

        called = True

        return 17

    monkeypatch.setattr(
        application,
        "list_models",
        fake_list_models,
    )

    result = main(
        (
            "model",
            "list",
        )
    )

    assert result == 17
    assert called


def test_cli_dispatches_model_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identifiers: list[str] = []

    def fake_show_model(
        identifier: str,
    ) -> int:
        identifiers.append(identifier)

        return 23

    monkeypatch.setattr(
        application,
        "show_model",
        fake_show_model,
    )

    result = main(
        (
            "model",
            "show",
            FIRST_IDENTIFIER,
        )
    )

    assert result == 23

    assert identifiers == [
        FIRST_IDENTIFIER,
    ]


def test_cli_model_show_requires_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "model",
                "show",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "MODEL_IDENTIFIER" in captured.err


def test_cli_dispatches_model_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_list_portfolio_models() -> int:
        nonlocal called

        called = True

        return 29

    monkeypatch.setattr(
        application,
        "list_portfolio_models",
        fake_list_portfolio_models,
    )

    result = main(
        (
            "model",
            "portfolio",
        )
    )

    assert result == 29
    assert called


def test_cli_model_help_lists_authorize_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "model",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "authorize" in captured.out


def test_cli_dispatches_model_authorize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identifiers: list[str] = []

    def fake_authorize_model(
        identifier: str,
    ) -> int:
        identifiers.append(identifier)

        return 31

    monkeypatch.setattr(
        application,
        "authorize_model",
        fake_authorize_model,
    )

    result = main(
        (
            "model",
            "authorize",
            FIRST_IDENTIFIER,
        )
    )

    assert result == 31
    assert identifiers == [
        FIRST_IDENTIFIER,
    ]


def test_cli_model_authorize_requires_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "model",
                "authorize",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "MODEL_IDENTIFIER" in captured.err


def test_cli_model_help_lists_deauthorize_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "model",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "deauthorize" in captured.out


def test_cli_dispatches_model_deauthorize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identifiers: list[str] = []

    def fake_deauthorize_model(
        identifier: str,
    ) -> int:
        identifiers.append(identifier)

        return 37

    monkeypatch.setattr(
        application,
        "deauthorize_model",
        fake_deauthorize_model,
    )

    result = main(
        (
            "model",
            "deauthorize",
            FIRST_IDENTIFIER,
        )
    )

    assert result == 37
    assert identifiers == [
        FIRST_IDENTIFIER,
    ]


def test_cli_model_deauthorize_requires_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "model",
                "deauthorize",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "MODEL_IDENTIFIER" in captured.err


def test_cli_workflow_help_lists_optimize_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "optimize" in captured.out


def test_cli_dispatches_workflow_optimize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, object] = {}

    def fake_optimize_workflow(
        *,
        workflow_id: UUID,
        expected_value: JsonValue,
        target_latency_seconds: float,
        target_cost_usd: float,
        generations: int,
    ) -> int:
        received.update(
            {
                "workflow_id": workflow_id,
                "expected_value": expected_value,
                "target_latency_seconds": target_latency_seconds,
                "target_cost_usd": target_cost_usd,
                "generations": generations,
            }
        )

        return 37

    monkeypatch.setattr(
        application,
        "optimize_workflow",
        fake_optimize_workflow,
    )

    result = main(
        (
            "workflow",
            "optimize",
            str(WORKFLOW_ID),
            "--expected",
            '"success"',
            "--target-latency",
            "5.0",
            "--target-cost",
            "0.01",
            "--generations",
            "3",
        )
    )

    assert result == 37

    assert received == {
        "workflow_id": WORKFLOW_ID,
        "expected_value": "success",
        "target_latency_seconds": 5.0,
        "target_cost_usd": 0.01,
        "generations": 3,
    }


def test_cli_workflow_optimize_parses_structured_expected_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_values: list[JsonValue] = []

    def fake_optimize_workflow(
        *,
        workflow_id: UUID,
        expected_value: JsonValue,
        target_latency_seconds: float,
        target_cost_usd: float,
        generations: int,
    ) -> int:
        del (
            workflow_id,
            target_latency_seconds,
            target_cost_usd,
            generations,
        )

        expected_values.append(expected_value)

        return 0

    monkeypatch.setattr(
        application,
        "optimize_workflow",
        fake_optimize_workflow,
    )

    result = main(
        (
            "workflow",
            "optimize",
            str(WORKFLOW_ID),
            "--expected",
            '{"classification":"positive"}',
            "--target-latency",
            "5",
            "--target-cost",
            "0.01",
        )
    )

    assert result == 0
    assert expected_values == [
        {
            "classification": "positive",
        }
    ]


def test_cli_workflow_optimize_requires_scoring_targets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "optimize",
                str(WORKFLOW_ID),
                "--expected",
                '"success"',
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "--target-latency" in captured.err
    assert "--target-cost" in captured.err


def test_cli_workflow_optimize_rejects_invalid_expected_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(
        (
            SystemExit,
            ValueError,
        )
    ):
        main(
            (
                "workflow",
                "optimize",
                str(WORKFLOW_ID),
                "--expected",
                "{not-json}",
                "--target-latency",
                "5",
                "--target-cost",
                "0.01",
            )
        )

    capsys.readouterr()
