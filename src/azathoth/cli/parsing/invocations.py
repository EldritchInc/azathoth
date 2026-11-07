"""Production invocation command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

from azathoth.cli.output_format import DEFAULT_WORKFLOW_OUTPUT_FORMAT, WorkflowOutputFormat

INVOCATION_COMMAND = "invocation"

INVOCATION_ACTION_ATTRIBUTE = "invocation_action"

INVOCATION_ANNOTATIONS_ACTION = "annotations"
INVOCATION_RESUME_ACTION = "resume"
INVOCATION_SHOW_ACTION = "show"

INVOCATION_ID_ATTRIBUTE = "invocation_id"

INVOCATION_LINKS_ATTRIBUTE = "invocation_links"

INVOCATION_OUTPUT_ATTRIBUTE = "invocation_output"


def add_invocation_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add persisted production invocation commands to the Azathoth parser."""

    invocation_parser = commands.add_parser(
        INVOCATION_COMMAND,
        help="Inspect and resume production invocations.",
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

    invocation_show_parser.add_argument(
        "--links",
        dest=INVOCATION_LINKS_ATTRIBUTE,
        action="store_true",
        help=(
            "Follow each verified citation with a link to its place in its document; "
            "s3:// links are presigned and need AWS credentials."
        ),
    )

    invocation_annotations_parser = invocation_actions.add_parser(
        INVOCATION_ANNOTATIONS_ACTION,
        help=("Print every verified citation an invocation's run kept, as W3C Web Annotations."),
    )

    invocation_annotations_parser.add_argument(
        INVOCATION_ID_ATTRIBUTE,
        type=UUID,
        metavar="INVOCATION_ID",
        help="Production invocation UUID whose citations to export.",
    )

    invocation_resume_parser = invocation_actions.add_parser(
        INVOCATION_RESUME_ACTION,
        help="Resume an incomplete production invocation where its run stopped.",
    )

    invocation_resume_parser.add_argument(
        INVOCATION_ID_ATTRIBUTE,
        type=UUID,
        metavar="INVOCATION_ID",
        help="Production invocation UUID to resume.",
    )

    invocation_resume_parser.add_argument(
        "--output",
        dest=INVOCATION_OUTPUT_ATTRIBUTE,
        choices=tuple(output_format.value for output_format in WorkflowOutputFormat),
        default=DEFAULT_WORKFLOW_OUTPUT_FORMAT.value,
        help=(
            "Output format: jsonl streams step records and a terminal record "
            "(default), text prints the human-readable report, result prints "
            "only the result as JSON."
        ),
    )
