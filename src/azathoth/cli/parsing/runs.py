"""Run command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

RUN_COMMAND = "run"

RUN_ACTION_ATTRIBUTE = "run_action"

RUN_SHOW_ACTION = "show"

RUN_ID_ATTRIBUTE = "run_id"


def add_run_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add persisted workflow run commands to the Azathoth parser."""

    run_parser = commands.add_parser(
        RUN_COMMAND,
        help="Inspect persisted workflow runs.",
    )

    run_actions = run_parser.add_subparsers(
        dest=RUN_ACTION_ATTRIBUTE,
    )

    run_show_parser = run_actions.add_parser(
        RUN_SHOW_ACTION,
        help="Show one persisted workflow run with step evidence and resources.",
    )

    run_show_parser.add_argument(
        RUN_ID_ATTRIBUTE,
        type=UUID,
        metavar="RUN_ID",
        help="Workflow run UUID to inspect.",
    )
