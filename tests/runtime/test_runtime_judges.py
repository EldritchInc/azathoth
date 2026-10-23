"""Tests for resolving semantic judges from runtime composition."""

import asyncio

import pytest

from azathoth.evaluation import (
    ExpectedOutcome,
    JudgeEntry,
    JudgeRotation,
    OutcomeComparison,
    UnsupportedComparisonError,
)
from azathoth.providers import (
    LanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
)
from azathoth.runtime import (
    AzathothRuntime,
    AzathothRuntimeError,
    JudgeUnavailableError,
)
from azathoth.workflows import WorkflowCatalog
from tests.evaluation.test_semantic import (
    PASS_REPLY,
    ScriptedJudgeModel,
)

JUDGE = JudgeEntry(
    provider="judges",
    model="gamma",
)


def create_runtime(
    *,
    judges: JudgeRotation | None = None,
    authorized: bool = True,
    cataloged: bool = True,
    registered: bool = True,
    model: ScriptedJudgeModel | None = None,
) -> AzathothRuntime:
    """Create a runtime whose one judge model has the given availability."""

    language_models: dict[str, LanguageModel] = (
        {
            JUDGE.identifier: model if model is not None else ScriptedJudgeModel(),
        }
        if registered
        else {}
    )

    return AzathothRuntime(
        workflows=WorkflowCatalog(),
        models=ModelCatalog(
            models=(
                (
                    ModelMetadata(
                        provider="judges",
                        model="gamma",
                        display_name="Gamma Judge",
                        context_window_tokens=8_192,
                    ),
                )
                if cataloged
                else ()
            ),
        ),
        portfolio=ModelPortfolio(
            entries=(
                (
                    ModelPortfolioEntry(
                        provider="judges",
                        model="gamma",
                    ),
                )
                if authorized
                else ()
            ),
        ),
        language_models=LanguageModelRegistry(language_models),
        judges=judges,
    )


def create_rotation() -> JudgeRotation:
    """Create a one-judge rotation."""

    return JudgeRotation(
        entries=(JUDGE,),
    )


def test_runtime_has_empty_judge_rotation_by_default() -> None:
    assert create_runtime().judges == JudgeRotation()


def test_runtime_exposes_its_judge_rotation() -> None:
    assert create_runtime(judges=create_rotation()).judges == create_rotation()


def test_deterministic_evaluator_does_not_support_semantic() -> None:
    evaluator = create_runtime(judges=create_rotation()).outcome_evaluator()

    assert evaluator.supports(OutcomeComparison.EXACT)
    assert not evaluator.supports(OutcomeComparison.SEMANTIC)


def test_deterministic_evaluator_ignores_unusable_judges() -> None:
    evaluator = create_runtime(
        judges=create_rotation(),
        authorized=False,
        registered=False,
    ).outcome_evaluator()

    with pytest.raises(UnsupportedComparisonError):
        evaluator.require_supported(OutcomeComparison.SEMANTIC)


def test_semantic_evaluator_judges_with_the_resolved_model() -> None:
    model = ScriptedJudgeModel(PASS_REPLY)

    evaluator = create_runtime(
        judges=create_rotation(),
        model=model,
    ).outcome_evaluator(
        semantic=True,
    )

    evaluation = asyncio.run(
        evaluator.evaluate(
            ExpectedOutcome(
                description="The request succeeded.",
                value="done",
                comparison=OutcomeComparison.SEMANTIC,
            ),
            "It worked.",
        )
    )

    assert evaluation.evaluator_name == "semantic-judge"
    assert evaluation.passed
    assert len(model.prompts) == 1


def test_semantic_evaluator_still_supports_deterministic_comparisons() -> None:
    evaluator = create_runtime(
        judges=create_rotation(),
    ).outcome_evaluator(
        semantic=True,
    )

    for comparison in OutcomeComparison:
        assert evaluator.supports(comparison)


def test_semantic_evaluator_requires_configured_judges() -> None:
    with pytest.raises(
        JudgeUnavailableError,
        match="^No semantic judges are configured.$",
    ):
        create_runtime().outcome_evaluator(
            semantic=True,
        )


def test_semantic_evaluator_requires_authorized_judges() -> None:
    with pytest.raises(
        JudgeUnavailableError,
        match="^Judge model judges/gamma is not authorized.$",
    ):
        create_runtime(
            judges=create_rotation(),
            authorized=False,
        ).outcome_evaluator(
            semantic=True,
        )


def test_semantic_evaluator_requires_current_provider_model() -> None:
    with pytest.raises(
        JudgeUnavailableError,
        match="^Judge model judges/gamma is not currently available.$",
    ):
        create_runtime(
            judges=create_rotation(),
            cataloged=False,
        ).outcome_evaluator(
            semantic=True,
        )


def test_semantic_evaluator_requires_executable_language_model() -> None:
    with pytest.raises(
        JudgeUnavailableError,
        match="^Judge model judges/gamma is not currently available.$",
    ):
        create_runtime(
            judges=create_rotation(),
            registered=False,
        ).outcome_evaluator(
            semantic=True,
        )


def test_judge_unavailable_error_is_a_runtime_error() -> None:
    assert issubclass(JudgeUnavailableError, AzathothRuntimeError)
