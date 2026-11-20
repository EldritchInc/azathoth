"""Spend command-line parser construction (ADR 0132)."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path
from typing import Final
from uuid import UUID

SPEND_COMMAND: Final = "spend"

SPEND_SINCE_ATTRIBUTE: Final = "spend_since"

SPEND_UNTIL_ATTRIBUTE: Final = "spend_until"

SPEND_BY_ATTRIBUTE: Final = "spend_by"

SPEND_GROUP_ATTRIBUTE: Final = "spend_group"

SPEND_TIME_ZONE_ATTRIBUTE: Final = "spend_time_zone"

SPEND_WORKFLOW_ATTRIBUTE: Final = "spend_workflow"

SPEND_OUTPUT_ATTRIBUTE: Final = "spend_output"

SPEND_OUTPUT_FILE_ATTRIBUTE: Final = "spend_output_file"

SPEND_OUTPUTS: Final = ("text", "json", "csv")
"""How `azathoth spend` writes its report."""

SPEND_PERIOD_CHOICES: Final = ("day", "week", "month")
"""The periods a report can be grouped into, as `api.SpendPeriod` lists them."""

SPEND_GROUP_CHOICES: Final = ("workflow", "model", "provider", "source")
"""What a report can group spend by, as `api.SpendGroup` lists them."""


def add_spend_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add the spend command to the Azathoth parser."""

    spend_parser = commands.add_parser(
        SPEND_COMMAND,
        help=(
            "Show what this instance spent, by period in a time zone, billed and "
            "estimated apart (ADR 0132)."
        ),
    )

    spend_parser.add_argument(
        "--since",
        dest=SPEND_SINCE_ATTRIBUTE,
        metavar="DATE_OR_TIME",
        help=(
            "Where the report starts: a date, its midnight in the time zone, or an "
            "ISO 8601 time. By default, 30 days before --until."
        ),
    )

    spend_parser.add_argument(
        "--until",
        dest=SPEND_UNTIL_ATTRIBUTE,
        metavar="DATE_OR_TIME",
        help=(
            "Where the report ends, not included: a date or an ISO 8601 time. By "
            "default, the end of today."
        ),
    )

    spend_parser.add_argument(
        "--by",
        dest=SPEND_BY_ATTRIBUTE,
        choices=SPEND_PERIOD_CHOICES,
        default="day",
        help="How long each period is: a day, an ISO week starting Monday, or a month.",
    )

    spend_parser.add_argument(
        "--group",
        dest=SPEND_GROUP_ATTRIBUTE,
        choices=SPEND_GROUP_CHOICES,
        default="workflow",
        help="What each period's spend is grouped by.",
    )

    spend_parser.add_argument(
        "--time-zone",
        dest=SPEND_TIME_ZONE_ATTRIBUTE,
        metavar="IANA_ZONE",
        help=(
            "The time zone periods are read in, such as America/New_York. "
            "By default, this computer's."
        ),
    )

    spend_parser.add_argument(
        "--workflow",
        dest=SPEND_WORKFLOW_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Report only this workflow's spend.",
    )

    spend_parser.add_argument(
        "--output",
        dest=SPEND_OUTPUT_ATTRIBUTE,
        choices=SPEND_OUTPUTS,
        default="text",
        help=(
            "Output format: text (default), json writes the service API's SpendReport, "
            "csv writes a row for each group in each period, for a spreadsheet."
        ),
    )

    spend_parser.add_argument(
        "--output-file",
        dest=SPEND_OUTPUT_FILE_ATTRIBUTE,
        type=Path,
        metavar="PATH",
        help="Write the report to this file instead of standard output.",
    )
