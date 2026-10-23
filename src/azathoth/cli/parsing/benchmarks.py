"""Benchmark command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path
from uuid import UUID

from azathoth.cli.parsing.common import positive_integer
from azathoth.cli.parsing.workflows import (
    TARGET_COST_ATTRIBUTE,
    TARGET_LATENCY_ATTRIBUTE,
    WORKFLOW_ID_ATTRIBUTE,
)

BENCHMARK_COMMAND = "benchmark"

BENCHMARK_ACTION_ATTRIBUTE = "benchmark_action"

BENCHMARK_CASES_ACTION = "cases"
BENCHMARK_CASE_SHOW_ACTION = "case-show"
BENCHMARK_COMPARE_ACTION = "compare"
BENCHMARK_EXECUTION_SHOW_ACTION = "execution-show"
BENCHMARK_EXECUTIONS_ACTION = "executions"
BENCHMARK_IMPORT_ACTION = "import"
BENCHMARK_LIST_ACTION = "list"
BENCHMARK_RUN_ACTION = "run"
BENCHMARK_SHOW_ACTION = "show"

BENCHMARK_DOCUMENT_ATTRIBUTE = "benchmark_document"
BENCHMARK_ID_ATTRIBUTE = "benchmark_id"
BENCHMARK_CASE_ID_ATTRIBUTE = "benchmark_case_id"
BENCHMARK_EXECUTION_ID_ATTRIBUTE = "benchmark_execution_id"
BENCHMARK_EXECUTION_LIMIT_ATTRIBUTE = "benchmark_execution_limit"
BENCHMARK_WORKFLOW_IDS_ATTRIBUTE = "workflow_ids"


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

    benchmark_run_parser = benchmark_actions.add_parser(
        BENCHMARK_RUN_ACTION,
        help="Execute one configured workflow against a benchmark dataset.",
    )

    benchmark_run_parser.add_argument(
        BENCHMARK_ID_ATTRIBUTE,
        type=UUID,
        metavar="BENCHMARK_ID",
        help="Benchmark dataset UUID to execute.",
    )

    benchmark_run_parser.add_argument(
        "--workflow",
        dest=WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        required=True,
        metavar="WORKFLOW_ID",
        help="Configured workflow UUID to benchmark.",
    )

    benchmark_compare_parser = benchmark_actions.add_parser(
        BENCHMARK_COMPARE_ACTION,
        help="Compare configured workflows against one benchmark dataset.",
    )

    benchmark_compare_parser.add_argument(
        BENCHMARK_ID_ATTRIBUTE,
        type=UUID,
        metavar="BENCHMARK_ID",
        help="Benchmark dataset UUID to execute.",
    )

    benchmark_compare_parser.add_argument(
        "--workflow",
        dest=BENCHMARK_WORKFLOW_IDS_ATTRIBUTE,
        type=UUID,
        action="append",
        required=True,
        metavar="WORKFLOW_ID",
        help="Configured workflow UUID to compare. Repeat for each workflow.",
    )

    benchmark_compare_parser.add_argument(
        "--target-latency",
        dest=TARGET_LATENCY_ATTRIBUTE,
        type=float,
        required=True,
        metavar="SECONDS",
        help="Target workflow latency in seconds.",
    )

    benchmark_compare_parser.add_argument(
        "--target-cost",
        dest=TARGET_COST_ATTRIBUTE,
        type=float,
        required=True,
        metavar="USD",
        help="Target workflow execution cost in USD.",
    )

    benchmark_executions_parser = benchmark_actions.add_parser(
        BENCHMARK_EXECUTIONS_ACTION,
        help="List saved runs and comparisons of one benchmark, newest first.",
    )

    benchmark_executions_parser.add_argument(
        BENCHMARK_ID_ATTRIBUTE,
        type=UUID,
        metavar="BENCHMARK_ID",
        help="Benchmark dataset UUID whose executions to list.",
    )

    benchmark_executions_parser.add_argument(
        "--limit",
        dest=BENCHMARK_EXECUTION_LIMIT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="COUNT",
        help="Maximum number of most recent executions to list.",
    )

    benchmark_execution_show_parser = benchmark_actions.add_parser(
        BENCHMARK_EXECUTION_SHOW_ACTION,
        help="Show one saved benchmark run or comparison with every case.",
    )

    benchmark_execution_show_parser.add_argument(
        BENCHMARK_EXECUTION_ID_ATTRIBUTE,
        type=UUID,
        metavar="EXECUTION_ID",
        help="Benchmark execution UUID to inspect.",
    )
