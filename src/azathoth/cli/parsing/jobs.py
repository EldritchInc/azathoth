"""Job envelope command-line parser construction (ADR 0097)."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction

JOB_COMMAND = "job"

JOB_ACTION_ATTRIBUTE = "job_action"

JOB_RUN_ACTION = "run"

JOB_REQUEST_ATTRIBUTE = "job_request"

STANDARD_INPUT_REQUEST = "-"
"""The request argument that reads the request from standard input."""


def add_job_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add versioned job envelope commands to the Azathoth parser."""

    job_parser = commands.add_parser(
        JOB_COMMAND,
        help="Run versioned job requests.",
    )

    job_actions = job_parser.add_subparsers(
        dest=JOB_ACTION_ATTRIBUTE,
    )

    job_run_parser = job_actions.add_parser(
        JOB_RUN_ACTION,
        help="Run one job request and print its result envelope as JSON.",
    )

    job_run_parser.add_argument(
        JOB_REQUEST_ATTRIBUTE,
        metavar="FILE",
        help="Job request JSON file, or - to read it from standard input.",
    )
