"""Tests for benchmarks judging declared workflow results."""

import asyncio
from dataclasses import replace

import pytest

from azathoth.evaluation import BenchmarkCase
from azathoth.workflows import (
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowResultError,
)
from tests.workflows.test_benchmark_comparisons import (
    WORKFLOW_ID,
    create_candidate,
    create_mixed_dataset,
)


def test_benchmark_judges_declared_result() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_mixed_dataset(),
            create_candidate,
        )
    )

    assert result.cases_run == 3
    assert result.cases_passed == 2


def test_benchmark_rejects_candidate_without_declared_result() -> None:
    executed: list[BenchmarkCase] = []

    def undeclared_candidate(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        executed.append(case)

        return replace(
            create_candidate(case),
            result=None,
        )

    with pytest.raises(
        WorkflowResultError,
        match=f"^Workflow {WORKFLOW_ID} does not declare a result.$",
    ):
        asyncio.run(
            WorkflowBenchmarkRunner().run(
                create_mixed_dataset(),
                undeclared_candidate,
            )
        )

    assert len(executed) == 1
