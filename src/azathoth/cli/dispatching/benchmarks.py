"""Benchmark command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.benchmark_cases import SuppliedExpectedValue
from azathoth.cli.parsing import (
    BENCHMARK_ACTION_ATTRIBUTE,
    BENCHMARK_ADD_CASE_ACTION,
    BENCHMARK_CASE_COMPARISON_ATTRIBUTE,
    BENCHMARK_CASE_DESCRIPTION_ATTRIBUTE,
    BENCHMARK_CASE_EXPECTED_ATTRIBUTE,
    BENCHMARK_CASE_ID_ATTRIBUTE,
    BENCHMARK_CASE_SHOW_ACTION,
    BENCHMARK_CASE_SOURCE_RUN_ID_ATTRIBUTE,
    BENCHMARK_CASES_ACTION,
    BENCHMARK_COMPARE_ACTION,
    BENCHMARK_DOCUMENT_ATTRIBUTE,
    BENCHMARK_EXECUTION_ID_ATTRIBUTE,
    BENCHMARK_EXECUTION_LIMIT_ATTRIBUTE,
    BENCHMARK_EXECUTION_SHOW_ACTION,
    BENCHMARK_EXECUTIONS_ACTION,
    BENCHMARK_EXPORT_ACTION,
    BENCHMARK_HISTORY_ACTION,
    BENCHMARK_HISTORY_LIMIT_ATTRIBUTE,
    BENCHMARK_ID_ATTRIBUTE,
    BENCHMARK_IMPORT_ACTION,
    BENCHMARK_LIST_ACTION,
    BENCHMARK_REVISION_ATTRIBUTE,
    BENCHMARK_RUN_ACTION,
    BENCHMARK_SHOW_ACTION,
    BENCHMARK_WORKFLOW_IDS_ATTRIBUTE,
    TARGET_COST_ATTRIBUTE,
    TARGET_LATENCY_ATTRIBUTE,
    WORKFLOW_ID_ATTRIBUTE,
)
from azathoth.evaluation.models import OutcomeComparison

BenchmarkAddCaseHandler = Callable[..., int]
BenchmarkIdentifierHandler = Callable[[UUID], int]
BenchmarkCaseHandler = Callable[[UUID, UUID], int]
BenchmarkListHandler = Callable[[], int]
BenchmarkImportHandler = Callable[[Path], int]
BenchmarkRunHandler = Callable[..., int]
BenchmarkCompareHandler = Callable[..., int]
BenchmarkExecutionListHandler = Callable[..., int]
BenchmarkRevisionHandler = Callable[..., int]


def dispatch_benchmark_command(
    arguments: Namespace,
    *,
    add_benchmark_case: BenchmarkAddCaseHandler,
    compare_benchmarks: BenchmarkCompareHandler,
    export_benchmark: BenchmarkRevisionHandler,
    import_benchmark: BenchmarkImportHandler,
    list_benchmark_cases: BenchmarkIdentifierHandler,
    list_benchmark_executions: BenchmarkExecutionListHandler,
    list_benchmark_history: BenchmarkExecutionListHandler,
    list_benchmarks: BenchmarkListHandler,
    run_benchmark: BenchmarkRunHandler,
    show_benchmark: BenchmarkRevisionHandler,
    show_benchmark_case: BenchmarkCaseHandler,
    show_benchmark_execution: BenchmarkIdentifierHandler,
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
            ),
            revision=_benchmark_revision(arguments),
        )

    if action == BENCHMARK_EXPORT_ACTION:
        return export_benchmark(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            ),
            revision=_benchmark_revision(arguments),
        )

    if action == BENCHMARK_HISTORY_ACTION:
        return list_benchmark_history(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            ),
            limit=cast(
                int | None,
                getattr(
                    arguments,
                    BENCHMARK_HISTORY_LIMIT_ATTRIBUTE,
                    None,
                ),
            ),
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

    if action == BENCHMARK_ADD_CASE_ACTION:
        return add_benchmark_case(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            ),
            run_id=cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_CASE_SOURCE_RUN_ID_ATTRIBUTE,
                ),
            ),
            comparison=OutcomeComparison(
                cast(
                    str,
                    getattr(
                        arguments,
                        BENCHMARK_CASE_COMPARISON_ATTRIBUTE,
                    ),
                )
            ),
            expected=_supplied_expected_value(arguments),
            description=cast(
                str | None,
                getattr(
                    arguments,
                    BENCHMARK_CASE_DESCRIPTION_ATTRIBUTE,
                    None,
                ),
            ),
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

    if action == BENCHMARK_EXECUTIONS_ACTION:
        return list_benchmark_executions(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_ID_ATTRIBUTE,
                ),
            ),
            limit=cast(
                int | None,
                getattr(
                    arguments,
                    BENCHMARK_EXECUTION_LIMIT_ATTRIBUTE,
                    None,
                ),
            ),
        )

    if action == BENCHMARK_EXECUTION_SHOW_ACTION:
        return show_benchmark_execution(
            cast(
                UUID,
                getattr(
                    arguments,
                    BENCHMARK_EXECUTION_ID_ATTRIBUTE,
                ),
            )
        )

    return None


def _benchmark_revision(
    arguments: Namespace,
) -> int | None:
    """Return the requested imported benchmark revision number, if any."""

    return cast(
        int | None,
        getattr(
            arguments,
            BENCHMARK_REVISION_ATTRIBUTE,
            None,
        ),
    )


def _supplied_expected_value(
    arguments: Namespace,
) -> SuppliedExpectedValue | None:
    """Return the expected value supplied for a new benchmark case, if any.

    The option is absent from the parsed arguments unless it was given, so a
    supplied JSON null is still an expected value.
    """

    if not hasattr(
        arguments,
        BENCHMARK_CASE_EXPECTED_ATTRIBUTE,
    ):
        return None

    return SuppliedExpectedValue(
        value=cast(
            JsonValue,
            getattr(
                arguments,
                BENCHMARK_CASE_EXPECTED_ATTRIBUTE,
            ),
        )
    )
