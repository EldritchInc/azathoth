"""Parsers for `workflow diff`, `tool diff` and `benchmark diff` (ADR 0133)."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

from azathoth.cli.output_format import DiffOutputFormat
from azathoth.cli.parsing.common import positive_integer

DIFF_ACTION = "diff"

DIFF_BEFORE_ATTRIBUTE = "diff_before"
DIFF_AFTER_ATTRIBUTE = "diff_after"
DIFF_OUTPUT_ATTRIBUTE = "diff_output"


def add_diff_parser(
    actions: _SubParsersAction[ArgumentParser],
    *,
    noun: str,
    id_attribute: str,
    id_metavar: str,
    version_attribute: str | None = None,
) -> ArgumentParser:
    """Add a `diff` action comparing two revisions of one `noun` to a command's actions.

    A tool's revisions belong to one exact version, so it is named with
    `--version` into `version_attribute`, as `tool export` names it.
    """

    parser = actions.add_parser(
        DIFF_ACTION,
        help=f"Show what differs between two imported revisions of one {noun}.",
    )

    parser.add_argument(
        id_attribute,
        type=UUID,
        metavar=id_metavar,
        help=f"{noun.capitalize()} UUID whose revisions to compare.",
    )

    parser.add_argument(
        DIFF_BEFORE_ATTRIBUTE,
        type=positive_integer,
        metavar="BEFORE",
        help="Revision number to compare from.",
    )

    parser.add_argument(
        DIFF_AFTER_ATTRIBUTE,
        type=positive_integer,
        metavar="AFTER",
        help="Revision number to compare to.",
    )

    if version_attribute is not None:
        parser.add_argument(
            "--version",
            dest=version_attribute,
            required=True,
            metavar="VERSION",
            help="Exact tool version whose revisions to compare.",
        )

    parser.add_argument(
        "--output",
        dest=DIFF_OUTPUT_ATTRIBUTE,
        choices=[output.value for output in DiffOutputFormat],
        default=DiffOutputFormat.TEXT.value,
        help=(
            "Output format: text writes a line per change; json writes the service API's "
            "RevisionComparison."
        ),
    )

    return parser


__all__ = [
    "DIFF_ACTION",
    "DIFF_AFTER_ATTRIBUTE",
    "DIFF_BEFORE_ATTRIBUTE",
    "DIFF_OUTPUT_ATTRIBUTE",
    "add_diff_parser",
]
