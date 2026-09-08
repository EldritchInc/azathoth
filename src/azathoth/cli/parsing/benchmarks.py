"""Benchmark command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path
from uuid import UUID

BENCHMARK_COMMAND = "benchmark"

BENCHMARK_ACTION_ATTRIBUTE = "benchmark_action"

BENCHMARK_CASES_ACTION = "cases"
BENCHMARK_CASE_SHOW_ACTION = "case-show"
BENCHMARK_IMPORT_ACTION = "import"
BENCHMARK_DOCUMENT_ATTRIBUTE = "benchmark_document"
BENCHMARK_LIST_ACTION = "list"
BENCHMARK_SHOW_ACTION = "show"

BENCHMARK_ID_ATTRIBUTE = "benchmark_id"
BENCHMARK_CASE_ID_ATTRIBUTE = "benchmark_case_id"


def add_benchmark_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add benchmark commands to the Azathoth parser."""

    benchmark_parser = commands.add_parser(
        BENCHMARK_COMMAND,
        help="Inspect and operate durable benchmark datasets.",
    )

    benchmark_actions = benchmark_parser.add_subparsers(
        dest=BENCHMARK_ACTION_ATTRIBUTE,
    )

    benchmark_actions.add_parser(
        BENCHMARK_LIST_ACTION,
        help="List durable benchmark datasets.",
    )

    benchmark_show_parser = benchmark_actions.add_parser(
        BENCHMARK_SHOW_ACTION,
        help="Show one durable benchmark dataset.",
    )

    benchmark_show_parser.add_argument(
        BENCHMARK_ID_ATTRIBUTE,
        type=UUID,
        metavar="BENCHMARK_ID",
        help="Benchmark dataset UUID to inspect.",
    )

    benchmark_cases_parser = benchmark_actions.add_parser(
        BENCHMARK_CASES_ACTION,
        help="List cases in one durable benchmark dataset.",
    )

    benchmark_cases_parser.add_argument(
        BENCHMARK_ID_ATTRIBUTE,
        type=UUID,
        metavar="BENCHMARK_ID",
        help="Benchmark dataset UUID to inspect.",
    )

    benchmark_case_show_parser = benchmark_actions.add_parser(
        BENCHMARK_CASE_SHOW_ACTION,
        help="Show one case in one durable benchmark dataset.",
    )

    benchmark_case_show_parser.add_argument(
        BENCHMARK_ID_ATTRIBUTE,
        type=UUID,
        metavar="BENCHMARK_ID",
        help="Benchmark dataset UUID containing the case.",
    )

    benchmark_case_show_parser.add_argument(
        BENCHMARK_CASE_ID_ATTRIBUTE,
        type=UUID,
        metavar="CASE_ID",
        help="Benchmark case UUID to inspect.",
    )

    benchmark_import_parser = benchmark_actions.add_parser(
        BENCHMARK_IMPORT_ACTION,
        help="Import one durable benchmark dataset.",
    )

    benchmark_import_parser.add_argument(
        BENCHMARK_DOCUMENT_ATTRIBUTE,
        type=Path,
        metavar="FILE",
        help="Benchmark dataset JSON document to import.",
    )
