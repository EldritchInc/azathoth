"""Run command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

from azathoth.cli.parsing.common import json_value

RUN_COMMAND = "run"

RUN_ACTION_ATTRIBUTE = "run_action"

RUN_FEEDBACK_ACTION = "feedback"
RUN_SHOW_ACTION = "show"

RUN_ID_ATTRIBUTE = "run_id"
RUN_FEEDBACK_CORRECTED_OUTPUT_ATTRIBUTE = "run_feedback_corrected_output"
RUN_FEEDBACK_DISPOSITION_ATTRIBUTE = "run_feedback_disposition"
RUN_FEEDBACK_REASON_ATTRIBUTE = "run_feedback_reason"

RUN_FEEDBACK_GOOD = "good"
RUN_FEEDBACK_BAD = "bad"


def add_run_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add persisted workflow run commands to the Azathoth parser."""

    run_parser = commands.add_parser(
        RUN_COMMAND,
        help="Inspect and judge persisted workflow runs.",
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

    run_feedback_parser = run_actions.add_parser(
        RUN_FEEDBACK_ACTION,
        help="Record one good or bad judgment about a persisted workflow run.",
    )

    run_feedback_parser.add_argument(
        RUN_ID_ATTRIBUTE,
        type=UUID,
        metavar="RUN_ID",
        help="Workflow run UUID to judge.",
    )

    disposition = run_feedback_parser.add_mutually_exclusive_group(
        required=True,
    )

    disposition.add_argument(
        "--good",
        dest=RUN_FEEDBACK_DISPOSITION_ATTRIBUTE,
        action="store_const",
        const=RUN_FEEDBACK_GOOD,
        help="Judge the run as good.",
    )

    disposition.add_argument(
        "--bad",
        dest=RUN_FEEDBACK_DISPOSITION_ATTRIBUTE,
        action="store_const",
        const=RUN_FEEDBACK_BAD,
        help="Judge the run as bad. Requires --reason.",
    )

    run_feedback_parser.add_argument(
        "--reason",
        dest=RUN_FEEDBACK_REASON_ATTRIBUTE,
        default=None,
        metavar="TEXT",
        help="Why the run was judged this way.",
    )

    run_feedback_parser.add_argument(
        "--corrected-output",
        dest=RUN_FEEDBACK_CORRECTED_OUTPUT_ATTRIBUTE,
        type=json_value,
        default=None,
        metavar="JSON",
        help="What the run should have produced, as JSON. Only with --bad.",
    )
