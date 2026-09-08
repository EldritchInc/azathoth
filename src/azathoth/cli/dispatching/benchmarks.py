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
    BENCHMARK_DOCUMENT_ATTRIBUTE,
    BENCHMARK_ID_ATTRIBUTE,
    BENCHMARK_IMPORT_ACTION,
    BENCHMARK_LIST_ACTION,
    BENCHMARK_SHOW_ACTION,
)

BenchmarkIdentifierHandler = Callable[[UUID], int]
BenchmarkCaseHandler = Callable[[UUID, UUID], int]
BenchmarkListHandler = Callable[[], int]
BenchmarkImportHandler = Callable[[Path], int]


def dispatch_benchmark_command(
    arguments: Namespace,
    *,
    import_benchmark: BenchmarkImportHandler,
    list_benchmark_cases: BenchmarkIdentifierHandler,
    list_benchmarks: BenchmarkListHandler,
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

    return None
