"""Tests for the Azathoth CLI module entry point."""

import subprocess
import sys

from azathoth import __version__


def test_cli_module_displays_version() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "azathoth.cli",
            "--version",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0

    assert result.stdout == (f"azathoth {__version__}\n")

    assert result.stderr == ""


def test_cli_module_displays_help() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "azathoth.cli",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0

    assert result.stdout.startswith("usage: azathoth")

    assert result.stderr == ""
