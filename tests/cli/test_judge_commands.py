"""Tests for parsing and dispatching semantic judge commands."""

import pytest

import azathoth.cli.application as application
from azathoth.cli import (
    build_parser,
    main,
)

IDENTIFIER = "openrouter/example/alpha"


def test_judge_help_lists_actions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "judge",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0
    assert "add" in captured.out
    assert "list" in captured.out
    assert "remove" in captured.out


def test_judge_parser_accepts_add_and_remove_identifiers() -> None:
    parser = build_parser()

    added = parser.parse_args(
        (
            "judge",
            "add",
            IDENTIFIER,
        )
    )
    removed = parser.parse_args(
        (
            "judge",
            "remove",
            IDENTIFIER,
        )
    )

    assert added.judge_action == "add"
    assert added.judge_identifier == IDENTIFIER
    assert removed.judge_action == "remove"
    assert removed.judge_identifier == IDENTIFIER


def test_judge_add_requires_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "judge",
                "add",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert "MODEL_IDENTIFIER" in captured.err


def test_cli_dispatches_judge_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_add_judge(
        identifier: str,
    ) -> int:
        calls.append(("add", identifier))

        return 11

    def fake_remove_judge(
        identifier: str,
    ) -> int:
        calls.append(("remove", identifier))

        return 12

    def fake_list_judges() -> int:
        calls.append(("list", None))

        return 13

    monkeypatch.setattr(
        application,
        "add_judge",
        fake_add_judge,
    )
    monkeypatch.setattr(
        application,
        "remove_judge",
        fake_remove_judge,
    )
    monkeypatch.setattr(
        application,
        "list_judges",
        fake_list_judges,
    )

    assert main(("judge", "add", IDENTIFIER)) == 11
    assert main(("judge", "remove", IDENTIFIER)) == 12
    assert main(("judge", "list")) == 13

    assert calls == [
        ("add", IDENTIFIER),
        ("remove", IDENTIFIER),
        ("list", None),
    ]


def test_judge_without_action_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(("judge",)) == 0

    captured = capsys.readouterr()

    assert "usage: azathoth" in captured.out
