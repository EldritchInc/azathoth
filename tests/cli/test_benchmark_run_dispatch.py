"""Tests for benchmark run command parsing and dispatch."""

from argparse import Namespace
from pathlib import Path
from uuid import UUID

from azathoth.cli import build_parser
from azathoth.cli.dispatching import dispatch_benchmark_command

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")


def unused_import_benchmark(
    _document: Path,
) -> int:
    """Fail when an unrelated benchmark handler is dispatched."""

    raise AssertionError("benchmark import should not be dispatched")


def unused_benchmark_identifier(
    _benchmark_id: UUID,
) -> int:
    """Fail when an unrelated benchmark handler is dispatched."""

    raise AssertionError("benchmark identifier handler should not be dispatched")


def unused_benchmark_case(
    _benchmark_id: UUID,
    _case_id: UUID,
) -> int:
    """Fail when benchmark case inspection is dispatched."""

    raise AssertionError("benchmark case handler should not be dispatched")


def unused_list_benchmarks() -> int:
    """Fail when benchmark listing is dispatched."""

    raise AssertionError("benchmark list should not be dispatched")


def unused_compare_benchmarks(
    *,
    benchmark_id: UUID,
    workflow_ids: tuple[UUID, ...],
    output_name: str,
    target_latency_seconds: float,
    target_cost_usd: float,
) -> int:
    """Fail when benchmark comparison is unexpectedly dispatched."""

    del (
        benchmark_id,
        workflow_ids,
        output_name,
        target_latency_seconds,
        target_cost_usd,
    )

    raise AssertionError("benchmark compare should not be dispatched")


def test_benchmark_run_parser_records_dataset_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "run",
            str(BENCHMARK_ID),
            "--workflow",
            str(WORKFLOW_ID),
            "--output",
            "classification",
        )
    )

    assert arguments.benchmark_action == "run"
    assert arguments.benchmark_id == BENCHMARK_ID


def test_benchmark_run_parser_records_workflow_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "run",
            str(BENCHMARK_ID),
            "--workflow",
            str(WORKFLOW_ID),
            "--output",
            "classification",
        )
    )

    assert arguments.workflow_id == WORKFLOW_ID


def test_benchmark_run_parser_records_output_name() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "run",
            str(BENCHMARK_ID),
            "--workflow",
            str(WORKFLOW_ID),
            "--output",
            "classification",
        )
    )

    assert arguments.benchmark_output == "classification"


def test_benchmark_run_dispatches_complete_execution_request() -> None:
    arguments = Namespace(
        benchmark_action="run",
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
        benchmark_output="classification",
    )

    calls: list[
        tuple[
            UUID,
            UUID,
            str,
        ]
    ] = []

    def run_benchmark(
        *,
        benchmark_id: UUID,
        workflow_id: UUID,
        output_name: str,
    ) -> int:
        calls.append(
            (
                benchmark_id,
                workflow_id,
                output_name,
            )
        )

        return 17

    result = dispatch_benchmark_command(
        arguments,
        compare_benchmarks=unused_compare_benchmarks,
        import_benchmark=unused_import_benchmark,
        list_benchmark_cases=unused_benchmark_identifier,
        list_benchmarks=unused_list_benchmarks,
        run_benchmark=run_benchmark,
        show_benchmark=unused_benchmark_identifier,
        show_benchmark_case=unused_benchmark_case,
    )

    assert result == 17

    assert calls == [
        (
            BENCHMARK_ID,
            WORKFLOW_ID,
            "classification",
        )
    ]
