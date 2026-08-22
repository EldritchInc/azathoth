"""Command-line application for Azathoth."""

from argparse import ArgumentParser
from collections.abc import Sequence

from azathoth import __version__


def build_parser() -> ArgumentParser:
    """Build the Azathoth command-line parser."""

    parser = ArgumentParser(
        prog="azathoth",
        description=("Empirical optimization for context-aware AI workflows."),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the Azathoth command-line application."""

    parser = build_parser()

    parser.parse_args(argv)

    parser.print_help()

    return 0
