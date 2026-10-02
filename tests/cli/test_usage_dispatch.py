"""Tests for usage command parsing and dispatch."""

from uuid import UUID

import pytest

import azathoth.cli.application as application
from azathoth.cli import (
    build_parser,
    main,
)

MODEL_IDENTIFIER = "openrouter/example-model"

TOOL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_model_usage_parser_records_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "model",
            "usage",
            MODEL_IDENTIFIER,
        )
    )

    assert arguments.model_action == "usage"
    assert arguments.model_identifier == MODEL_IDENTIFIER


def test_cli_dispatches_model_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identifiers: list[str] = []

    def fake_model_usage(
        identifier: str,
    ) -> int:
        identifiers.append(identifier)

        return 31

    monkeypatch.setattr(
        application,
        "model_usage",
        fake_model_usage,
    )

    result = main(
        (
            "model",
            "usage",
            MODEL_IDENTIFIER,
        )
    )

    assert result == 31
    assert identifiers == [
        MODEL_IDENTIFIER,
    ]


def test_cli_model_usage_requires_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "model",
                "usage",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "MODEL_IDENTIFIER" in captured.err


def test_cli_model_help_lists_usage_action(
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
    assert ",usage}" in captured.out


def test_tool_usage_parser_records_tool_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "tool",
            "usage",
            str(TOOL_ID),
        )
    )

    assert arguments.tool_action == "usage"
    assert arguments.tool_id == TOOL_ID


def test_cli_dispatches_tool_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_ids: list[UUID] = []

    def fake_tool_usage(
        tool_id: UUID,
    ) -> int:
        tool_ids.append(tool_id)

        return 37

    monkeypatch.setattr(
        application,
        "tool_usage",
        fake_tool_usage,
    )

    result = main(
        (
            "tool",
            "usage",
            str(TOOL_ID),
        )
    )

    assert result == 37
    assert tool_ids == [
        TOOL_ID,
    ]


def test_cli_tool_usage_rejects_invalid_tool_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "tool",
                "usage",
                "not-a-uuid",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert captured.out == ""
    assert "TOOL_ID" in captured.err


def test_cli_tool_help_lists_usage_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "tool",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert ",usage}" in captured.out
