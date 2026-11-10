"""Tests that the sensitivity messages the guide quotes are the ones Azathoth gives (ADR 0123)."""

from pathlib import Path

import pytest

from azathoth.sensitivity import (
    RESTRICTED_REFUSAL_HINT,
    UNKNOWN_DATA_POLICY,
    Sensitivity,
    SensitivityError,
    require_no_lower,
    restricted_refusal,
)

README = Path(__file__).parents[2] / "src" / "azathoth" / "sensitivity" / "README.md"

MODEL = "openrouter/example/frontier"


def quoted(
    line: str,
) -> bool:
    return f"\n{line}\n" in README.read_text(encoding="utf-8")


def test_the_lowering_refusal_is_quoted_exactly() -> None:
    with pytest.raises(SensitivityError) as caught:
        require_no_lower(
            Sensitivity.INTERNAL,
            Sensitivity.RESTRICTED,
            source="Run <RUN_ID>",
            derived="a case made from it",
        )

    assert quoted(str(caught.value))


def test_the_restricted_refusal_and_its_hint_are_quoted_exactly() -> None:
    assert quoted(restricted_refusal(MODEL, UNKNOWN_DATA_POLICY))
    assert quoted(RESTRICTED_REFUSAL_HINT.format(model=MODEL))
