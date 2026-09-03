"""Tests for in-memory production invocation persistence."""

from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationRepository,
    ProductionInvocationSuccess,
    require_production_invocation_repository,
)

FIRST_INVOCATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_INVOCATION_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

UNKNOWN_INVOCATION_ID = UUID("77777777-7777-7777-7777-777777777777")


def create_invocation(
    *,
    invocation_id: UUID = FIRST_INVOCATION_ID,
    workflow_id: UUID = FIRST_WORKFLOW_ID,
) -> ProductionInvocation:
    """Create deterministic production invocation."""

    return ProductionInvocation(
        id=invocation_id,
        workflow_id=workflow_id,
        initial_context=Context(),
    )


def test_in_memory_production_invocation_repository_satisfies_protocol() -> None:
    repository: ProductionInvocationRepository = InMemoryProductionInvocationRepository()

    assert (
        require_production_invocation_repository(
            repository,
        )
        is repository
    )


def test_in_memory_production_invocation_repository_starts_empty() -> None:
    repository = InMemoryProductionInvocationRepository()

    assert repository.invocations() == ()
    assert repository.get(FIRST_INVOCATION_ID) is None
    assert repository.result(FIRST_INVOCATION_ID) is None


def test_in_memory_production_invocation_repository_saves_invocation() -> None:
    repository = InMemoryProductionInvocationRepository()

    invocation = create_invocation()

    repository.save(
        invocation,
    )

    assert repository.get(FIRST_INVOCATION_ID) is invocation
    assert repository.invocations() == (invocation,)


def test_in_memory_repository_preserves_invocation_insertion_order() -> None:
    repository = InMemoryProductionInvocationRepository()

    first = create_invocation()

    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.invocations() == (
        first,
        second,
    )


def test_in_memory_repository_rejects_duplicate_invocation() -> None:
    repository = InMemoryProductionInvocationRepository()

    invocation = create_invocation()

    repository.save(invocation)

    with pytest.raises(
        ValueError,
        match=f"Production invocation {FIRST_INVOCATION_ID} already exists",
    ):
        repository.save(invocation)


def test_in_memory_repository_filters_invocations_by_workflow() -> None:
    repository = InMemoryProductionInvocationRepository()

    first = create_invocation()

    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.invocations_for_workflow(FIRST_WORKFLOW_ID) == (first,)
    assert repository.invocations_for_workflow(SECOND_WORKFLOW_ID) == (second,)


def test_in_memory_repository_saves_success_result() -> None:
    repository = InMemoryProductionInvocationRepository()

    invocation = create_invocation()

    repository.save(invocation)

    result = ProductionInvocationSuccess(
        invocation_id=invocation.id,
        result={
            "classification": "positive",
        },
    )

    repository.save_result(result)

    assert repository.result(invocation.id) is result


def test_in_memory_repository_saves_failure_result() -> None:
    repository = InMemoryProductionInvocationRepository()

    invocation = create_invocation()

    repository.save(invocation)

    result = ProductionInvocationFailure(
        invocation_id=invocation.id,
        error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
        message="Workflow execution failed.",
    )

    repository.save_result(result)

    assert repository.result(invocation.id) is result


def test_in_memory_repository_rejects_result_for_unknown_invocation() -> None:
    repository = InMemoryProductionInvocationRepository()

    result = ProductionInvocationSuccess(
        invocation_id=UNKNOWN_INVOCATION_ID,
        result="success",
    )

    with pytest.raises(
        ValueError,
        match=f"Production invocation {UNKNOWN_INVOCATION_ID} does not exist",
    ):
        repository.save_result(result)


def test_in_memory_repository_rejects_second_terminal_result() -> None:
    repository = InMemoryProductionInvocationRepository()

    invocation = create_invocation()

    repository.save(invocation)

    success = ProductionInvocationSuccess(
        invocation_id=invocation.id,
        result="success",
    )

    failure = ProductionInvocationFailure(
        invocation_id=invocation.id,
        error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
        message="Workflow execution failed.",
    )

    repository.save_result(success)

    with pytest.raises(
        ValueError,
        match=(f"Production invocation {FIRST_INVOCATION_ID} already has a terminal result"),
    ):
        repository.save_result(failure)

    assert repository.result(invocation.id) is success
