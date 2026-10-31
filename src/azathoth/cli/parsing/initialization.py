"""Initialization command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction

INIT_COMMAND = "init"


def add_init_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add the init command to the Azathoth parser."""

    commands.add_parser(
        INIT_COMMAND,
        help="Create the database if needed and install the standard tools.",
    )
