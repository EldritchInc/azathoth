"""Experiment command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

EXPERIMENT_COMMAND = "experiment"

EXPERIMENT_ACTION_ATTRIBUTE = "experiment_action"

EXPERIMENT_SHOW_ACTION = "show"

EXPERIMENT_ID_ATTRIBUTE = "experiment_id"


def add_experiment_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add persisted workflow experiment commands to the Azathoth parser."""

    experiment_parser = commands.add_parser(
        EXPERIMENT_COMMAND,
        help="Inspect persisted workflow experiments.",
    )

    experiment_actions = experiment_parser.add_subparsers(
        dest=EXPERIMENT_ACTION_ATTRIBUTE,
    )

    experiment_show_parser = experiment_actions.add_parser(
        EXPERIMENT_SHOW_ACTION,
        help="Show one persisted experiment with every observation in rank order.",
    )

    experiment_show_parser.add_argument(
        EXPERIMENT_ID_ATTRIBUTE,
        type=UUID,
        metavar="EXPERIMENT_ID",
        help="Workflow experiment UUID to inspect.",
    )
