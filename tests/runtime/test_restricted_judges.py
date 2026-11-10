"""Tests that judges of restricted cases must be allowed to receive them (ADR 0123)."""

from uuid import UUID

import pytest

from azathoth.cli.benchmark_execution import judged_sensitivity
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.providers import ModelPortfolio, ModelPortfolioEntry
from azathoth.runtime import AzathothRuntime, JudgeUnavailableError
from azathoth.sensitivity import PRIVATE_DATA_POLICY, DataPolicy, Sensitivity
from tests.runtime.test_runtime_judges import JUDGE, create_rotation, create_runtime


def judged_by(
    policy: DataPolicy,
) -> AzathothRuntime:
    """Return a runtime whose one judge's portfolio entry declares this policy."""

    runtime = create_runtime(judges=create_rotation())

    return AzathothRuntime(
        workflows=runtime.workflows,
        models=runtime.models,
        portfolio=ModelPortfolio(
            entries=(
                ModelPortfolioEntry(
                    provider=JUDGE.provider,
                    model=JUDGE.model,
                    data_policy=policy,
                ),
            )
        ),
        language_models=runtime.language_models,
        judges=runtime.judges,
    )


def test_an_undeclared_judge_cannot_judge_restricted_cases() -> None:
    with pytest.raises(JudgeUnavailableError) as caught:
        judged_by(DataPolicy()).outcome_evaluator(
            semantic=True,
            sensitivity=Sensitivity.RESTRICTED,
        )

    assert str(caught.value) == (
        "Judge model judges/gamma cannot receive restricted input: its portfolio entry does not "
        "say whether its provider retains data, and does not say whether it trains on data. "
        "If its provider neither retains nor trains on data, declare that with "
        "`azathoth model policy judges/gamma --no-retention --no-training`; otherwise choose a "
        "model that may receive restricted input."
    )


def test_a_private_judge_judges_restricted_cases() -> None:
    evaluator = judged_by(PRIVATE_DATA_POLICY).outcome_evaluator(
        semantic=True,
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert evaluator.supports(OutcomeComparison.SEMANTIC)


@pytest.mark.parametrize("label", [None, Sensitivity.PUBLIC, Sensitivity.INTERNAL])
def test_any_authorized_judge_judges_other_cases(
    label: Sensitivity | None,
) -> None:
    evaluator = judged_by(DataPolicy()).outcome_evaluator(semantic=True, sensitivity=label)

    assert evaluator.supports(OutcomeComparison.SEMANTIC)


def test_a_deterministic_evaluator_needs_no_judge_whatever_the_label() -> None:
    evaluator = judged_by(DataPolicy()).outcome_evaluator(sensitivity=Sensitivity.RESTRICTED)

    assert not evaluator.supports(OutcomeComparison.SEMANTIC)


def case(
    number: int,
    comparison: OutcomeComparison,
    sensitivity: Sensitivity | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        id=UUID(int=number),
        input=number,
        expected=ExpectedOutcome(description="Right.", value=number, comparison=comparison),
        sensitivity=sensitivity,
    )


@pytest.mark.parametrize(
    ("cases", "label"),
    [
        (
            (
                case(1, OutcomeComparison.EXACT, Sensitivity.RESTRICTED),
                case(2, OutcomeComparison.SEMANTIC, Sensitivity.PUBLIC),
            ),
            Sensitivity.PUBLIC,
        ),
        (
            (
                case(1, OutcomeComparison.SEMANTIC, Sensitivity.RESTRICTED),
                case(2, OutcomeComparison.SEMANTIC, Sensitivity.PUBLIC),
            ),
            Sensitivity.RESTRICTED,
        ),
        ((case(1, OutcomeComparison.SEMANTIC),), Sensitivity.INTERNAL),
        ((case(1, OutcomeComparison.EXACT, Sensitivity.RESTRICTED),), Sensitivity.INTERNAL),
    ],
    ids=["exact-restricted", "semantic-restricted", "unlabelled", "no-semantic-cases"],
)
def test_judges_are_sent_only_what_the_semantic_cases_hold(
    cases: tuple[BenchmarkCase, ...],
    label: Sensitivity,
) -> None:
    dataset = BenchmarkDataset(name="claims", description="Claims.", cases=cases)

    assert judged_sensitivity(dataset) is label
