"""Production invocation command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

INVOCATION_COMMAND = "invocation"

INVOCATION_ACTION_ATTRIBUTE = "invocation_action"

INVOCATION_SHOW_ACTION = "show"

INVOCATION_ID_ATTRIBUTE = "invocation_id"


def add_invocation_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add persisted production invocation commands to the Azathoth parser."""

    invocation_parser = commands.add_parser(
        INVOCATION_COMMAND,
        help="Inspect persisted production invocations.",
    )

    invocation_actions = invocation_parser.add_subparsers(
        dest=INVOCATION_ACTION_ATTRIBUTE,
    )

    invocation_show_parser = invocation_actions.add_parser(
        INVOCATION_SHOW_ACTION,
        help="Show one production invocation with its input, outcome, and run.",
    )

    invocation_show_parser.add_argument(
        INVOCATION_ID_ATTRIBUTE,
        type=UUID,
        metavar="INVOCATION_ID",
        help="Production invocation UUID to inspect.",
    )
