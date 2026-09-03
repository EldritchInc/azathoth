"""Tests for SQLite production invocation run persistence."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.workflows import (
    ProductionInvocationRun,
    ProductionInvocationRunRepository,
    SQLiteProductionInvocationRunRepository,
)

FIRST_INVOCATION_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_INVOCATION_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_RUN_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_RUN_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_repository(
    path: Path,
) -> SQLiteProductionInvocationRunRepository:
    """Create SQLite invocation run persistence."""

    return SQLiteProductionInvocationRunRepository(
        path,
    )


def create_association(
    *,
    invocation_id: UUID,
    run_id: UUID,
) -> ProductionInvocationRun:
    """Create one deterministic invocation run association."""

    return ProductionInvocationRun(
        invocation_id=invocation_id,
        run_id=run_id,
    )


def test_sqlite_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: ProductionInvocationRunRepository = create_repository(
        tmp_path / "azathoth.db",
    )

    assert repository.associations() == ()


def test_sqlite_repository_returns_saved_association(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "azathoth.db",
    )

    association = create_association(
        invocation_id=FIRST_INVOCATION_ID,
        run_id=FIRST_RUN_ID,
    )

    repository.save(
        association,
    )

    assert repository.get(FIRST_INVOCATION_ID) == association


def test_sqlite_repository_returns_none_for_unknown_invocation(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "azathoth.db",
    )

    assert repository.get(FIRST_INVOCATION_ID) is None


def test_sqlite_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "azathoth.db",
    )

    first = create_association(
        invocation_id=FIRST_INVOCATION_ID,
        run_id=FIRST_RUN_ID,
    )

    second = create_association(
        invocation_id=SECOND_INVOCATION_ID,
        run_id=SECOND_RUN_ID,
    )

    repository.save(
        first,
    )

    repository.save(
        second,
    )

    assert repository.associations() == (
        first,
        second,
    )


def test_sqlite_repository_rejects_second_run_for_invocation(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "azathoth.db",
    )

    repository.save(
        create_association(
            invocation_id=FIRST_INVOCATION_ID,
            run_id=FIRST_RUN_ID,
        )
    )

    with pytest.raises(
        ValueError,
        match="already has a workflow run",
    ):
        repository.save(
            create_association(
                invocation_id=FIRST_INVOCATION_ID,
                run_id=SECOND_RUN_ID,
            )
        )


def test_sqlite_repository_survives_reconstruction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"

    first_repository = create_repository(
        path,
    )

    association = create_association(
        invocation_id=FIRST_INVOCATION_ID,
        run_id=FIRST_RUN_ID,
    )

    first_repository.save(
        association,
    )

    reconstructed = create_repository(
        path,
    )

    assert reconstructed.get(FIRST_INVOCATION_ID) == association

    assert reconstructed.associations() == (association,)
