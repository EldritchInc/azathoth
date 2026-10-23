"""Semantic judge command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction

JUDGE_COMMAND = "judge"

JUDGE_ACTION_ATTRIBUTE = "judge_action"

JUDGE_ADD_ACTION = "add"
JUDGE_LIST_ACTION = "list"
JUDGE_REMOVE_ACTION = "remove"

JUDGE_IDENTIFIER_ATTRIBUTE = "judge_identifier"


def add_judge_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add semantic judge commands to the Azathoth parser."""

    judge_parser = commands.add_parser(
        JUDGE_COMMAND,
        help="Operate the rotation of models that judge semantic outcomes.",
    )

    judge_actions = judge_parser.add_subparsers(
        dest=JUDGE_ACTION_ATTRIBUTE,
    )

    judge_add_parser = judge_actions.add_parser(
        JUDGE_ADD_ACTION,
        help="Add one authorized, currently available model to the judge rotation.",
    )

    judge_add_parser.add_argument(
        JUDGE_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to add as a judge.",
    )

    judge_actions.add_parser(
        JUDGE_LIST_ACTION,
        help="List the judge rotation in order.",
    )

    judge_remove_parser = judge_actions.add_parser(
        JUDGE_REMOVE_ACTION,
        help="Remove one model from the judge rotation.",
    )

    judge_remove_parser.add_argument(
        JUDGE_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to remove from the rotation.",
    )
