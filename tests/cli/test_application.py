"""Tests for the Azathoth command-line application."""

from collections.abc import Sequence

import pytest

import azathoth.cli.application as application
from azathoth import __version__
from azathoth.cli import (
    build_parser,
    main,
)

FIRST_IDENTIFIER = "openrouter/example/model"


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
