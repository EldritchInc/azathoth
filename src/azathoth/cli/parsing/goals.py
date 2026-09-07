"""Goal command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

GOAL_COMMAND = "goal"

GOAL_ACTION_ATTRIBUTE = "goal_action"

GOAL_LIST_ACTION = "list"
GOAL_SHOW_ACTION = "show"

GOAL_ID_ATTRIBUTE = "goal_id"


def add_goal_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add goal commands to the Azathoth parser."""

    goal_parser = commands.add_parser(
        GOAL_COMMAND,
        help="Inspect and operate durable reusable goals.",
    )

    goal_actions = goal_parser.add_subparsers(
        dest=GOAL_ACTION_ATTRIBUTE,
    )

    goal_actions.add_parser(
        GOAL_LIST_ACTION,
        help="List durable reusable goals.",
    )

    goal_show_parser = goal_actions.add_parser(
        GOAL_SHOW_ACTION,
        help="Show one durable reusable goal.",
    )

    goal_show_parser.add_argument(
        GOAL_ID_ATTRIBUTE,
        type=UUID,
        metavar="GOAL_ID",
        help="Goal UUID to inspect.",
    )
