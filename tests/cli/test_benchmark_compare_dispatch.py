"""Tests for benchmark compare parsing and dispatch."""

from argparse import Namespace
from pathlib import Path
from uuid import UUID

from azathoth.cli import build_parser
from azathoth.cli.dispatching import dispatch_benchmark_command

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")


def unused_import_benchmark(
    _document: Path,
) -> int:
    """Fail when benchmark import is unexpectedly dispatched."""

    raise AssertionError("benchmark import should not be dispatched")


def unused_benchmark_identifier(
    _benchmark_id: UUID,
) -> int:
    """Fail when an identifier-only handler is dispatched."""

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


def unused_run_benchmark(
    *,
    benchmark_id: UUID,
    workflow_id: UUID,
    output_name: str,
) -> int:
    """Fail when benchmark run is unexpectedly dispatched."""

    del (
        benchmark_id,
        workflow_id,
        output_name,
    )

    raise AssertionError("benchmark run should not be dispatched")


def test_benchmark_compare_parser_records_dataset_identifier() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "compare",
            str(BENCHMARK_ID),
            "--workflow",
            str(FIRST_WORKFLOW_ID),
            "--workflow",
            str(SECOND_WORKFLOW_ID),
            "--output",
            "classification",
            "--target-latency",
            "5",
            "--target-cost",
            "0.001",
        )
    )

    assert arguments.benchmark_action == "compare"
    assert arguments.benchmark_id == BENCHMARK_ID


def test_benchmark_compare_parser_records_workflow_identifiers() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "compare",
            str(BENCHMARK_ID),
            "--workflow",
            str(FIRST_WORKFLOW_ID),
            "--workflow",
            str(SECOND_WORKFLOW_ID),
            "--output",
            "classification",
            "--target-latency",
            "5",
            "--target-cost",
            "0.001",
        )
    )

    assert arguments.workflow_ids == [
        FIRST_WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    ]


def test_benchmark_compare_parser_records_output_and_targets() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "compare",
            str(BENCHMARK_ID),
            "--workflow",
            str(FIRST_WORKFLOW_ID),
            "--workflow",
            str(SECOND_WORKFLOW_ID),
            "--output",
            "classification",
            "--target-latency",
            "5",
            "--target-cost",
            "0.001",
        )
    )

    assert arguments.benchmark_output == "classification"
    assert arguments.target_latency_seconds == 5.0
    assert arguments.target_cost_usd == 0.001


def test_benchmark_compare_dispatches_complete_request() -> None:
    arguments = Namespace(
        benchmark_action="compare",
        benchmark_id=BENCHMARK_ID,
        workflow_ids=[
            FIRST_WORKFLOW_ID,
            SECOND_WORKFLOW_ID,
        ],
        benchmark_output="classification",
        target_latency_seconds=5.0,
        target_cost_usd=0.001,
    )

    calls: list[
        tuple[
            UUID,
            tuple[UUID, ...],
            str,
            float,
            float,
        ]
    ] = []

    def compare_benchmarks(
        *,
        benchmark_id: UUID,
        workflow_ids: tuple[UUID, ...],
        output_name: str,
        target_latency_seconds: float,
        target_cost_usd: float,
    ) -> int:
        calls.append(
            (
                benchmark_id,
                workflow_ids,
                output_name,
                target_latency_seconds,
                target_cost_usd,
            )
        )

        return 19

    result = dispatch_benchmark_command(
        arguments,
        compare_benchmarks=compare_benchmarks,
        import_benchmark=unused_import_benchmark,
        list_benchmark_cases=unused_benchmark_identifier,
        list_benchmarks=unused_list_benchmarks,
        run_benchmark=unused_run_benchmark,
        show_benchmark=unused_benchmark_identifier,
        show_benchmark_case=unused_benchmark_case,
    )

    assert result == 19

    assert calls == [
        (
            BENCHMARK_ID,
            (
                FIRST_WORKFLOW_ID,
                SECOND_WORKFLOW_ID,
            ),
            "classification",
            5.0,
            0.001,
        )
    ]
