"""Tests that the restricted-input refusals the guides quote are the ones given (ADR 0123)."""

from pathlib import Path

import pytest

from azathoth.prompting import RestrictedInputRefusedError
from azathoth.runtime import JudgeUnavailableError
from azathoth.sensitivity import DataPolicy, Sensitivity
from tests.prompting.test_context_candidates import FIRST_IDENTIFIER
from tests.prompting.test_restricted_input import (
    STEP_ID,
    RecordingModel,
    run_in,
    step,
    strategy,
)
from tests.runtime.test_restricted_judges import judged_by
from tests.runtime.test_runtime_judges import JUDGE

PACKAGES = Path(__file__).parents[2] / "src" / "azathoth"


def quoted(
    package: str,
    line: str,
) -> bool:
    return f"\n{line}\n" in (PACKAGES / package / "README.md").read_text(encoding="utf-8")


def step_refusal() -> str:
    with pytest.raises(RestrictedInputRefusedError) as caught:
        run_in(step(Sensitivity.RESTRICTED), strategy(RecordingModel(), DataPolicy()))

    return str(caught.value).replace(str(STEP_ID), "<STEP_ID>")


@pytest.mark.parametrize(
    ("package", "model"),
    [("prompting", "<MODEL>"), ("cli", "<MODEL_IDENTIFIER>")],
)
def test_the_step_refusal_is_quoted_exactly(
    package: str,
    model: str,
) -> None:
    assert quoted(package, step_refusal().replace(FIRST_IDENTIFIER, model))


def test_the_judge_refusal_is_quoted_exactly() -> None:
    with pytest.raises(JudgeUnavailableError) as caught:
        judged_by(DataPolicy()).outcome_evaluator(
            semantic=True,
            sensitivity=Sensitivity.RESTRICTED,
        )

    assert quoted("runtime", str(caught.value).replace(JUDGE.identifier, "<MODEL_IDENTIFIER>"))
