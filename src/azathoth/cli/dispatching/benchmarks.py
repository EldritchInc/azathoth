"""Benchmark command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from azathoth.cli.parsing import (
    BENCHMARK_ACTION_ATTRIBUTE,
    BENCHMARK_CASE_ID_ATTRIBUTE,
    BENCHMARK_CASE_SHOW_ACTION,
    BENCHMARK_CASES_ACTION,
    BENCHMARK_COMPARE_ACTION,
    BENCHMARK_DOCUMENT_ATTRIBUTE,
    BENCHMARK_ID_ATTRIBUTE,
    BENCHMARK_IMPORT_ACTION,
    BENCHMARK_LIST_ACTION,
    BENCHMARK_OUTPUT_ATTRIBUTE,
    BENCHMARK_RUN_ACTION,
    BENCHMARK_SHOW_ACTION,
    BENCHMARK_WORKFLOW_IDS_ATTRIBUTE,
    TARGET_COST_ATTRIBUTE,
    TARGET_LATENCY_ATTRIBUTE,
    WORKFLOW_ID_ATTRIBUTE,
)

BenchmarkIdentifierHandler = Callable[[UUID], int]
BenchmarkCaseHandler = Callable[[UUID, UUID], int]
BenchmarkListHandler = Callable[[], int]
BenchmarkImportHandler = Callable[[Path], int]
BenchmarkRunHandler = Callable[..., int]
BenchmarkCompareHandler = Callable[..., int]


def dispatch_benchmark_command(
    arguments: Namespace,
    *,
    compare_benchmarks: BenchmarkCompareHandler,
    import_benchmark: BenchmarkImportHandler,
    list_benchmark_cases: BenchmarkIdentifierHandler,
    list_benchmarks: BenchmarkListHandler,
    run_benchmark: BenchmarkRunHandler,
    show_benchmark: BenchmarkIdentifierHandler,
    show_benchmark_case: BenchmarkCaseHandler,
) -> int | None:
    """Dispatch one parsed benchmark command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            BENCHMARK_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == BENCHMARK_LIST_ACTION:
        return list_benchmarks()

    if action == BENCHMARK_SHOW_ACTION:
        return show_benchmark(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            )
        )

    if action == BENCHMARK_CASES_ACTION:
        return list_benchmark_cases(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            )
        )

    if action == BENCHMARK_CASE_SHOW_ACTION:
        return show_benchmark_case(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            ),
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_CASE_ID_ATTRIBUTE,
                ),
            ),
        )

    if action == BENCHMARK_IMPORT_ACTION:
        return import_benchmark(
            cast(
                Path,
                getattr(
                    arguments,
                    BENCHMARK_DOCUMENT_ATTRIBUTE,
                ),
            )
        )

    if action == BENCHMARK_RUN_ACTION:
        return run_benchmark(
            benchmark_id=cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            ),
            workflow_id=cast(
                UUID,
                getattr(
                    arguments,
                    WORKFLOW_ID_ATTRIBUTE,
                ),
            ),
            output_name=cast(
                str,
                getattr(
                    arguments,
                    BENCHMARK_OUTPUT_ATTRIBUTE,
                ),
            ),
        )

    if action == BENCHMARK_COMPARE_ACTION:
        return compare_benchmarks(
            benchmark_id=cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            ),
            workflow_ids=tuple(
                cast(
                    list[UUID],
                    getattr(
                        arguments,
                        BENCHMARK_WORKFLOW_IDS_ATTRIBUTE,
                    ),
                )
            ),
            output_name=cast(
                str,
                getattr(
                    arguments,
                    BENCHMARK_OUTPUT_ATTRIBUTE,
                ),
            ),
            target_latency_seconds=cast(
                float,
                getattr(
                    arguments,
                    TARGET_LATENCY_ATTRIBUTE,
                ),
            ),
            target_cost_usd=cast(
                float,
                getattr(
                    arguments,
                    TARGET_COST_ATTRIBUTE,
                ),
            ),
        )

    return None
