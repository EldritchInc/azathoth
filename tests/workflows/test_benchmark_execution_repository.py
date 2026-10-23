"""Tests for in-memory and SQLite benchmark execution repositories."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.evaluation import OutcomeComparison
from azathoth.workflows import (
    InMemoryWorkflowBenchmarkExecutionRepository,
    SQLiteWorkflowBenchmarkExecutionRepository,
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionCase,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkExecutionRecord,
    WorkflowBenchmarkExecutionRepository,
    WorkflowCandidateSignature,
    WorkflowMetadata,
    WorkflowScorecard,
    WorkflowScoringPolicy,
    require_workflow_benchmark_execution_repository,
)

FIRST_EXECUTION_ID = UUID("e1e1e1e1-e1e1-e1e1-e1e1-e1e1e1e1e1e1")
SECOND_EXECUTION_ID = UUID("e2e2e2e2-e2e2-e2e2-e2e2-e2e2e2e2e2e2")
THIRD_EXECUTION_ID = UUID("e3e3e3e3-e3e3-e3e3-e3e3-e3e3e3e3e3e3")

FIRST_BENCHMARK_ID = UUID("b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1")
SECOND_BENCHMARK_ID = UUID("b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2")

FIRST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
THIRD_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")

FIRST_CASE_ID = UUID("c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1")
SECOND_CASE_ID = UUID("c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2")

POLICY = WorkflowScoringPolicy(
    target_latency_seconds=2.0,
    target_cost_usd=0.01,
)

RECORDED_AT = datetime(
    2026,
    10,
    23,
    9,
    0,
    tzinfo=UTC,
)


def identifier(
    group: int,
    index: int,
) -> UUID:
    """Return a deterministic identifier distinct per group and index."""

    return UUID(f"{group:08x}-0000-4000-8000-{index:012x}")


def create_candidate(
    *,
    workflow_id: UUID,
    group: int,
    score: float | None,
) -> WorkflowBenchmarkExecutionCandidate:
    """Create one candidate judged on two cases.

    Runs, evaluations, and the candidate identity are derived from the group,
    so every candidate built with a distinct group is distinct evidence.
    """

    return WorkflowBenchmarkExecutionCandidate(
        id=identifier(group, 0),
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow {workflow_id}",
            description="Execute a benchmarked workflow.",
        ),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=workflow_id,
            strategy_ids=(STRATEGY_ID,),
        ),
        cases=tuple(
            WorkflowBenchmarkExecutionCase(
                case_id=case_id,
                comparison=OutcomeComparison.EXACT,
                run_id=identifier(group, 100 + index),
                evaluation_id=identifier(group, 200 + index),
                passed=index == 0,
            )
            for index, case_id in enumerate((FIRST_CASE_ID, SECOND_CASE_ID))
        ),
        scorecard=(
            WorkflowScorecard(
                quality_score=score,
                reliability_score=score,
                latency_score=score,
                cost_score=score,
                overall_score=score,
                rationale="Deterministic test score.",
            )
            if score is not None
            else None
        ),
    )


def create_run_execution(
    *,
    execution_id: UUID,
    benchmark_id: UUID,
    workflow_id: UUID,
    group: int,
) -> WorkflowBenchmarkExecutionRecord:
    """Create one recorded benchmark run."""

    return WorkflowBenchmarkExecutionRecord(
        id=execution_id,
        benchmark_id=benchmark_id,
        kind=WorkflowBenchmarkExecutionKind.RUN,
        candidates=(
            create_candidate(
                workflow_id=workflow_id,
                group=group,
                score=None,
            ),
        ),
        recorded_at=RECORDED_AT,
    )


def create_compare_execution(
    *,
    execution_id: UUID,
    benchmark_id: UUID,
    workflow_ids: tuple[UUID, UUID],
    groups: tuple[int, int],
) -> WorkflowBenchmarkExecutionRecord:
    """Create one recorded comparison of two workflows."""

    candidates = (
        create_candidate(
            workflow_id=workflow_ids[0],
            group=groups[0],
            score=0.8,
        ),
        create_candidate(
            workflow_id=workflow_ids[1],
            group=groups[1],
            score=0.4,
        ),
    )

    return WorkflowBenchmarkExecutionRecord(
        id=execution_id,
        benchmark_id=benchmark_id,
        kind=WorkflowBenchmarkExecutionKind.COMPARE,
        candidates=candidates,
        ranking=tuple(candidate.id for candidate in candidates),
        scoring_policy=POLICY,
        recorded_at=RECORDED_AT,
    )


def create_executions() -> tuple[WorkflowBenchmarkExecutionRecord, ...]:
    """Create three executions across two benchmarks and three workflows.

    The first benchmark is run against the first workflow, then compares the
    first and second workflows. The second benchmark is run against the third
    workflow.
    """

    return (
        create_run_execution(
            execution_id=FIRST_EXECUTION_ID,
            benchmark_id=FIRST_BENCHMARK_ID,
            workflow_id=FIRST_WORKFLOW_ID,
            group=1,
        ),
        create_compare_execution(
            execution_id=SECOND_EXECUTION_ID,
            benchmark_id=FIRST_BENCHMARK_ID,
            workflow_ids=(
                FIRST_WORKFLOW_ID,
                SECOND_WORKFLOW_ID,
            ),
            groups=(2, 3),
        ),
        create_run_execution(
            execution_id=THIRD_EXECUTION_ID,
            benchmark_id=SECOND_BENCHMARK_ID,
            workflow_id=THIRD_WORKFLOW_ID,
            group=4,
        ),
    )


def create_repositories(
    tmp_path: Path,
) -> tuple[WorkflowBenchmarkExecutionRepository, ...]:
    """Return one empty repository of each implementation."""

    return (
        InMemoryWorkflowBenchmarkExecutionRepository(),
        SQLiteWorkflowBenchmarkExecutionRepository(
            tmp_path / "azathoth.db",
        ),
    )


def save_all(
    repository: WorkflowBenchmarkExecutionRepository,
    executions: tuple[WorkflowBenchmarkExecutionRecord, ...],
) -> None:
    """Save executions in order."""

    for execution in executions:
        repository.save(execution)


def test_repositories_save_and_get_executions(
    tmp_path: Path,
) -> None:
    """Saved executions are returned unchanged by identifier."""

    executions = create_executions()

    for repository in create_repositories(tmp_path):
        save_all(
            repository,
            executions,
        )

        assert repository.get(SECOND_EXECUTION_ID) == executions[1]


def test_repositories_return_none_for_unknown_execution(
    tmp_path: Path,
) -> None:
    """An unknown execution identifier resolves to nothing."""

    for repository in create_repositories(tmp_path):
        assert repository.get(FIRST_EXECUTION_ID) is None


def test_repositories_preserve_insertion_order(
    tmp_path: Path,
) -> None:
    """All executions are listed in the order they were saved."""

    executions = create_executions()

    for repository in create_repositories(tmp_path):
        save_all(
            repository,
            executions,
        )

        assert repository.executions() == executions


def test_repositories_filter_by_benchmark(
    tmp_path: Path,
) -> None:
    """Executions are found by the benchmark they executed."""

    executions = create_executions()

    for repository in create_repositories(tmp_path):
        save_all(
            repository,
            executions,
        )

        assert repository.executions_for_benchmark(FIRST_BENCHMARK_ID) == executions[:2]
        assert repository.executions_for_benchmark(SECOND_BENCHMARK_ID) == executions[2:]
        assert repository.executions_for_benchmark(UUID(int=0)) == ()


def test_repositories_filter_by_workflow(
    tmp_path: Path,
) -> None:
    """Executions are found by every workflow they judged, once each."""

    executions = create_executions()

    for repository in create_repositories(tmp_path):
        save_all(
            repository,
            executions,
        )

        assert repository.executions_for_workflow(FIRST_WORKFLOW_ID) == executions[:2]
        assert repository.executions_for_workflow(SECOND_WORKFLOW_ID) == (executions[1],)
        assert repository.executions_for_workflow(THIRD_WORKFLOW_ID) == (executions[2],)
        assert repository.executions_for_workflow(UUID(int=0)) == ()


def test_repositories_find_execution_by_run(
    tmp_path: Path,
) -> None:
    """Every recorded run traces back to the execution that produced it."""

    executions = create_executions()

    for repository in create_repositories(tmp_path):
        save_all(
            repository,
            executions,
        )

        assert repository.execution_for_run(identifier(3, 101)) == executions[1]
        assert repository.execution_for_run(identifier(4, 100)) == executions[2]
        assert repository.execution_for_run(UUID(int=0)) is None


def test_repositories_reject_duplicate_execution(
    tmp_path: Path,
) -> None:
    """Saving an execution twice never replaces existing evidence."""

    executions = create_executions()

    for repository in create_repositories(tmp_path):
        repository.save(executions[0])

        with pytest.raises(
            ValueError,
            match=f"Benchmark execution {FIRST_EXECUTION_ID} already exists.",
        ):
            repository.save(executions[0])

        assert repository.executions() == executions[:1]


def test_sqlite_repository_persists_across_instances(
    tmp_path: Path,
) -> None:
    """A new repository over the same database sees earlier executions."""

    database = tmp_path / "azathoth.db"
    executions = create_executions()

    save_all(
        SQLiteWorkflowBenchmarkExecutionRepository(database),
        executions,
    )

    reopened = SQLiteWorkflowBenchmarkExecutionRepository(database)

    assert reopened.executions() == executions
    assert reopened.executions_for_workflow(SECOND_WORKFLOW_ID) == (executions[1],)


def test_sqlite_repository_indexes_every_case(
    tmp_path: Path,
) -> None:
    """Every case of every candidate is indexed exactly once."""

    database = tmp_path / "azathoth.db"
    repository = SQLiteWorkflowBenchmarkExecutionRepository(database)

    save_all(
        repository,
        create_executions(),
    )

    repository.save(
        create_run_execution(
            execution_id=UUID(int=1),
            benchmark_id=FIRST_BENCHMARK_ID,
            workflow_id=FIRST_WORKFLOW_ID,
            group=5,
        )
    )

    connection = sqlite3.connect(database)

    try:
        rows = connection.execute(
            """
            SELECT execution_id, candidate_id, workflow_id, case_id
            FROM workflow_benchmark_execution_cases
            WHERE execution_id = ?
            ORDER BY sequence
            """,
            (str(SECOND_EXECUTION_ID),),
        ).fetchall()

        total = connection.execute(
            "SELECT COUNT(*) FROM workflow_benchmark_execution_cases",
        ).fetchone()
    finally:
        connection.close()

    assert rows == [
        (
            str(SECOND_EXECUTION_ID),
            str(identifier(2, 0)),
            str(FIRST_WORKFLOW_ID),
            str(FIRST_CASE_ID),
        ),
        (
            str(SECOND_EXECUTION_ID),
            str(identifier(2, 0)),
            str(FIRST_WORKFLOW_ID),
            str(SECOND_CASE_ID),
        ),
        (
            str(SECOND_EXECUTION_ID),
            str(identifier(3, 0)),
            str(SECOND_WORKFLOW_ID),
            str(FIRST_CASE_ID),
        ),
        (
            str(SECOND_EXECUTION_ID),
            str(identifier(3, 0)),
            str(SECOND_WORKFLOW_ID),
            str(SECOND_CASE_ID),
        ),
    ]
    assert total == (10,)


def test_sqlite_repository_duplicate_save_writes_no_index_rows(
    tmp_path: Path,
) -> None:
    """A rejected duplicate leaves the case index unchanged."""

    database = tmp_path / "azathoth.db"
    repository = SQLiteWorkflowBenchmarkExecutionRepository(database)
    execution = create_executions()[1]

    repository.save(execution)

    with pytest.raises(ValueError):
        repository.save(execution)

    connection = sqlite3.connect(database)

    try:
        total = connection.execute(
            "SELECT COUNT(*) FROM workflow_benchmark_execution_cases",
        ).fetchone()
    finally:
        connection.close()

    assert total == (4,)


def test_sqlite_repository_rejects_non_text_payload(
    tmp_path: Path,
) -> None:
    """A corrupted payload fails loudly rather than decoding silently."""

    database = tmp_path / "azathoth.db"
    repository = SQLiteWorkflowBenchmarkExecutionRepository(database)

    connection = sqlite3.connect(database)

    try:
        connection.execute(
            """
            INSERT INTO workflow_benchmark_executions (
                execution_id,
                benchmark_id,
                payload
            )
            VALUES (?, ?, ?)
            """,
            (
                str(FIRST_EXECUTION_ID),
                str(FIRST_BENCHMARK_ID),
                b"not text",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        TypeError,
        match="Persisted benchmark execution payload was not text.",
    ):
        repository.get(FIRST_EXECUTION_ID)


def test_repositories_satisfy_protocol(
    tmp_path: Path,
) -> None:
    """Both implementations satisfy the repository protocol statically."""

    in_memory = require_workflow_benchmark_execution_repository(
        InMemoryWorkflowBenchmarkExecutionRepository(),
    )

    sqlite_repository = require_workflow_benchmark_execution_repository(
        SQLiteWorkflowBenchmarkExecutionRepository(
            tmp_path / "azathoth.db",
        ),
    )

    assert in_memory.executions() == ()
    assert sqlite_repository.executions() == ()
