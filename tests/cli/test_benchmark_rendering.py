"""Tests for human-readable benchmark execution rendering."""

from uuid import UUID

from azathoth.cli import render_workflow_benchmark_result
from azathoth.workflows import WorkflowBenchmarkResult

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")


class StubWorkflowBenchmarkResult(WorkflowBenchmarkResult):
    """Provide deterministic aggregate benchmark values for rendering."""

    @property
    def cases_run(self) -> int:
        """Return deterministic executed case count."""

        return 4

    @property
    def cases_passed(self) -> int:
        """Return deterministic passing case count."""

        return 3

    @property
    def accuracy(self) -> float:
        """Return deterministic benchmark accuracy."""

        return 0.75

    @property
    def total_tokens(self) -> int:
        """Return deterministic token usage."""

        return 120

    @property
    def total_latency_ms(self) -> int:
        """Return deterministic provider latency."""

        return 875

    @property
    def total_cost_usd(self) -> float:
        """Return deterministic model cost."""

        return 0.001234


def create_result() -> WorkflowBenchmarkResult:
    """Create deterministic aggregate benchmark evidence."""

    return StubWorkflowBenchmarkResult(
        dataset_id=BENCHMARK_ID,
    )


def test_benchmark_rendering_identifies_dataset_and_workflow() -> None:
    rendered = render_workflow_benchmark_result(
        create_result(),
        workflow_id=WORKFLOW_ID,
    )

    assert f"Benchmark ID: {BENCHMARK_ID}\n" in rendered
    assert f"Workflow ID: {WORKFLOW_ID}\n" in rendered


def test_benchmark_rendering_includes_evaluation_summary() -> None:
    rendered = render_workflow_benchmark_result(
        create_result(),
        workflow_id=WORKFLOW_ID,
    )

    assert "Cases Run: 4\n" in rendered
    assert "Cases Passed: 3\n" in rendered
    assert "Accuracy: 0.750000\n" in rendered


def test_benchmark_rendering_includes_execution_totals() -> None:
    rendered = render_workflow_benchmark_result(
        create_result(),
        workflow_id=WORKFLOW_ID,
    )

    assert "Total Tokens: 120\n" in rendered
    assert "Total Latency: 875 ms\n" in rendered
    assert "Total Cost: $0.001234" in rendered
