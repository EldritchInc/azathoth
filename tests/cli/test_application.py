"""Tests for the Azathoth command-line application."""

from collections.abc import Sequence

import pytest

from azathoth import __version__
from azathoth.cli import (
    build_parser,
    main,
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
