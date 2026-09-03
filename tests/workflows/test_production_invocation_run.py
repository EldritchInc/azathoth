"""Tests for production invocation run associations."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import ProductionInvocationRun

INVOCATION_ID = UUID("11111111-1111-1111-1111-111111111111")

RUN_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_production_invocation_run_records_identity() -> None:
    association = ProductionInvocationRun(
        invocation_id=INVOCATION_ID,
        run_id=RUN_ID,
    )

    assert association.invocation_id == INVOCATION_ID
    assert association.run_id == RUN_ID


def test_production_invocation_run_records_creation_time() -> None:
    association = ProductionInvocationRun(
        invocation_id=INVOCATION_ID,
        run_id=RUN_ID,
    )

    assert association.created_at.tzinfo is not None


def test_production_invocation_run_is_immutable() -> None:
    association = ProductionInvocationRun(
        invocation_id=INVOCATION_ID,
        run_id=RUN_ID,
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        association.__setattr__(
            "run_id",
            UUID("33333333-3333-3333-3333-333333333333"),
        )
