"""Tests for SQLite production invocation persistence."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationRepository,
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    require_production_invocation_repository,
)

FIRST_INVOCATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_INVOCATION_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_REVISION_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_REVISION_ID = UUID("66666666-6666-6666-6666-666666666666")

UNKNOWN_INVOCATION_ID = UUID("77777777-7777-7777-7777-777777777777")


def create_invocation(
    *,
    invocation_id: UUID = FIRST_INVOCATION_ID,
    workflow_id: UUID = FIRST_WORKFLOW_ID,
    revision_id: UUID = FIRST_REVISION_ID,
) -> ProductionInvocation:
    """Create deterministic production invocation."""

    return ProductionInvocation(
        id=invocation_id,
        workflow_id=workflow_id,
        production_revision_id=revision_id,
        initial_context=Context(),
    )


def create_repository(
    tmp_path: Path,
) -> SQLiteProductionInvocationRepository:
    """Create SQLite production invocation repository."""

    return SQLiteProductionInvocationRepository(
        tmp_path / "production.db",
    )


def test_sqlite_production_invocation_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: ProductionInvocationRepository = require_production_invocation_repository(
        create_repository(tmp_path)
    )

    assert repository.invocations() == ()


def test_sqlite_production_invocation_repository_starts_empty(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    assert repository.invocations() == ()
    assert repository.get(FIRST_INVOCATION_ID) is None
    assert repository.result(FIRST_INVOCATION_ID) is None


def test_sqlite_production_invocation_repository_saves_invocation(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    invocation = create_invocation()

    repository.save(invocation)

    restored = repository.get(invocation.id)

    assert restored == invocation
    assert restored is not invocation


def test_sqlite_repository_preserves_invocation_insertion_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_invocation()

    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        revision_id=SECOND_REVISION_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.invocations() == (
        first,
        second,
    )


def test_sqlite_repository_rejects_duplicate_invocation(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    invocation = create_invocation()

    repository.save(invocation)

    with pytest.raises(
        ValueError,
        match=f"Production invocation {FIRST_INVOCATION_ID} already exists",
    ):
        repository.save(invocation)


def test_sqlite_repository_filters_invocations_by_workflow(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_invocation()

    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        revision_id=SECOND_REVISION_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.invocations_for_workflow(FIRST_WORKFLOW_ID) == (first,)
    assert repository.invocations_for_workflow(SECOND_WORKFLOW_ID) == (second,)


def test_sqlite_repository_filters_invocations_by_revision(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    first = create_invocation()

    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID,
        revision_id=SECOND_REVISION_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.invocations_for_revision(FIRST_REVISION_ID) == (first,)
    assert repository.invocations_for_revision(SECOND_REVISION_ID) == (second,)


def test_sqlite_repository_persists_success_result(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    invocation = create_invocation()
    repository.save(invocation)

    result = ProductionInvocationSuccess(
        invocation_id=invocation.id,
        result={
            "classification": "positive",
        },
    )

    repository.save_result(result)

    restored = repository.result(invocation.id)

    assert restored == result
    assert isinstance(restored, ProductionInvocationSuccess)


def test_sqlite_repository_persists_failure_result(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    invocation = create_invocation()
    repository.save(invocation)

    result = ProductionInvocationFailure(
        invocation_id=invocation.id,
        error_code=ProductionInvocationErrorCode.MODEL_UNAVAILABLE,
        message="Production model unavailable.",
        metadata={
            "provider": "test-provider",
        },
    )

    repository.save_result(result)

    restored = repository.result(invocation.id)

    assert restored == result
    assert isinstance(restored, ProductionInvocationFailure)


def test_sqlite_repository_rejects_result_for_unknown_invocation(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    result = ProductionInvocationSuccess(
        invocation_id=UNKNOWN_INVOCATION_ID,
        result="success",
    )

    with pytest.raises(
        ValueError,
        match=f"Production invocation {UNKNOWN_INVOCATION_ID} does not exist",
    ):
        repository.save_result(result)


def test_sqlite_repository_rejects_second_terminal_result(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path)

    invocation = create_invocation()
    repository.save(invocation)

    first = ProductionInvocationSuccess(
        invocation_id=invocation.id,
        result="success",
    )

    second = ProductionInvocationFailure(
        invocation_id=invocation.id,
        error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
        message="Workflow execution failed.",
    )

    repository.save_result(first)

    with pytest.raises(
        ValueError,
        match=(f"Production invocation {FIRST_INVOCATION_ID} already has a terminal result"),
    ):
        repository.save_result(second)

    assert repository.result(invocation.id) == first


def test_sqlite_invocation_and_result_survive_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    invocation = create_invocation()

    result = ProductionInvocationSuccess(
        invocation_id=invocation.id,
        result={
            "answer": "success",
        },
    )

    repository = SQLiteProductionInvocationRepository(
        database,
    )

    repository.save(invocation)
    repository.save_result(result)

    reconstructed = SQLiteProductionInvocationRepository(
        database,
    )

    assert reconstructed.get(invocation.id) == invocation
    assert reconstructed.result(invocation.id) == result


def test_sqlite_invocation_queries_survive_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    first = create_invocation()

    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID,
        revision_id=SECOND_REVISION_ID,
    )

    repository = SQLiteProductionInvocationRepository(
        database,
    )

    repository.save(first)
    repository.save(second)

    reconstructed = SQLiteProductionInvocationRepository(
        database,
    )

    assert reconstructed.invocations() == (
        first,
        second,
    )

    assert reconstructed.invocations_for_workflow(FIRST_WORKFLOW_ID) == (
        first,
        second,
    )

    assert reconstructed.invocations_for_revision(FIRST_REVISION_ID) == (first,)

    assert reconstructed.invocations_for_revision(SECOND_REVISION_ID) == (second,)
