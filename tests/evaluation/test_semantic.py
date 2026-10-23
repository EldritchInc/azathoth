"""Tests for semantic evaluation by a rotation of language-model judges."""

import asyncio

import pytest

from azathoth.evaluation import (
    SEMANTIC_EVALUATOR_NAME,
    SEMANTIC_EVALUATOR_VERSION,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
    InvalidJudgeResponseError,
    JudgeEntry,
    JudgeRotation,
    OutcomeComparison,
    SemanticEvaluator,
    SemanticJudgingError,
    judge_call_count,
    judge_calls_cost_usd,
    parse_judge_verdict,
    semantic_judge_prompt,
)
from azathoth.providers import (
    ModelResponse,
    Prompt,
)

ALPHA = JudgeEntry(
    provider="judges",
    model="alpha",
)

BETA = JudgeEntry(
    provider="judges",
    model="beta",
)

GAMMA = JudgeEntry(
    provider="judges",
    model="gamma",
)

PASS_REPLY = '{"verdict": "pass", "reason": "Both say the request succeeded."}'

FAIL_REPLY = '{"verdict": "fail", "reason": "The actual answer reports a failure."}'


class ScriptedJudgeModel:
    """Reply with scripted text or raise scripted errors, recording every prompt."""

    def __init__(
        self,
        *replies: str | Exception,
        cost_usd: float = 0.001,
    ) -> None:
        self._replies = list(replies)
        self._cost_usd = cost_usd
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return or raise the next scripted reply."""

        self.prompts.append(prompt.text)

        reply = self._replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        return ModelResponse(
            text=reply,
            provider="judges",
            model="scripted",
            prompt_tokens=100,
            completion_tokens=10,
            total_tokens=110,
            latency_ms=250,
            estimated_cost_usd=self._cost_usd,
        )


def create_expected(
    value: str = "done",
) -> ExpectedOutcome:
    """Create one semantic expectation.

    With the three-judge rotation, the default expectation is assigned to beta
    first, so beta, gamma, then alpha is its try order.
    """

    return ExpectedOutcome(
        description="The request succeeded.",
        value=value,
        comparison=OutcomeComparison.SEMANTIC,
    )


def create_rotation() -> JudgeRotation:
    """Create a three-judge rotation."""

    return JudgeRotation(
        entries=(
            ALPHA,
            BETA,
            GAMMA,
        ),
    )


def create_evaluator(
    *,
    alpha: ScriptedJudgeModel | None = None,
    beta: ScriptedJudgeModel | None = None,
    gamma: ScriptedJudgeModel | None = None,
) -> SemanticEvaluator:
    """Create an evaluator whose judges follow the given scripts."""

    return SemanticEvaluator(
        rotation=create_rotation(),
        models={
            ALPHA.identifier: alpha if alpha is not None else ScriptedJudgeModel(),
            BETA.identifier: beta if beta is not None else ScriptedJudgeModel(),
            GAMMA.identifier: gamma if gamma is not None else ScriptedJudgeModel(),
        },
    )


def evaluate(
    evaluator: SemanticEvaluator,
    actual: str = "It worked.",
    expected: ExpectedOutcome | None = None,
) -> EvaluationResult:
    """Evaluate one actual value synchronously."""

    return asyncio.run(
        evaluator.evaluate(
            expected if expected is not None else create_expected(),
            actual,
        )
    )


def evidence_of(
    evaluation: EvaluationResult,
) -> dict[str, object]:
    """Return evaluation evidence by label."""

    return {item.label: item.value for item in evaluation.evidence}


def test_semantic_evaluator_identity() -> None:
    metadata = create_evaluator().metadata

    assert metadata.name == "semantic-judge"
    assert metadata.name == SEMANTIC_EVALUATOR_NAME
    assert metadata.version == "1.0.0"
    assert metadata.version == SEMANTIC_EVALUATOR_VERSION


def test_pass_verdict_passes_with_full_score() -> None:
    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel(PASS_REPLY),
        )
    )

    assert evaluation.evaluator_name == "semantic-judge"
    assert evaluation.evaluator_version == "1.0.0"
    assert evaluation.score == 1.0
    assert evaluation.threshold == 1.0
    assert evaluation.status is EvaluationStatus.PASSED
    assert evaluation.reason == (
        "Judge judges/beta found the actual value equivalent to the expected value: "
        "Both say the request succeeded."
    )


def test_fail_verdict_fails_with_zero_score() -> None:
    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel(FAIL_REPLY),
        )
    )

    assert evaluation.score == 0.0
    assert evaluation.status is EvaluationStatus.FAILED
    assert evaluation.reason == (
        "Judge judges/beta found the actual value not equivalent to the expected value: "
        "The actual answer reports a failure."
    )


def test_verdict_evidence_records_judge_and_usage() -> None:
    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel(PASS_REPLY),
        )
    )

    assert tuple(item.label for item in evaluation.evidence) == (
        "expected",
        "actual",
        "judge",
        "verdict",
        "judge_reason",
        "judge_calls",
    )

    evidence = evidence_of(evaluation)

    assert evidence["expected"] == "done"
    assert evidence["actual"] == "It worked."
    assert evidence["judge"] == "judges/beta"
    assert evidence["verdict"] == "pass"
    assert evidence["judge_reason"] == "Both say the request succeeded."
    assert evidence["judge_calls"] == [
        {
            "judge": "judges/beta",
            "status": "verdict",
            "detail": None,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
                "latency_ms": 250,
                "estimated_cost_usd": 0.001,
            },
        },
    ]


def test_expectation_is_judged_by_its_assigned_judge_only() -> None:
    alpha = ScriptedJudgeModel()
    beta = ScriptedJudgeModel(PASS_REPLY)
    gamma = ScriptedJudgeModel()

    evaluate(
        create_evaluator(
            alpha=alpha,
            beta=beta,
            gamma=gamma,
        )
    )

    assert len(beta.prompts) == 1
    assert alpha.prompts == []
    assert gamma.prompts == []


def test_every_candidate_meets_the_same_judge_for_one_expectation() -> None:
    beta = ScriptedJudgeModel(PASS_REPLY, FAIL_REPLY)

    evaluator = create_evaluator(
        beta=beta,
    )

    first = evaluate(
        evaluator,
        actual="It worked.",
    )
    second = evaluate(
        evaluator,
        actual="It failed.",
    )

    assert evidence_of(first)["judge"] == "judges/beta"
    assert evidence_of(second)["judge"] == "judges/beta"
    assert len(beta.prompts) == 2


def test_judge_error_falls_back_to_the_next_judge() -> None:
    gamma = ScriptedJudgeModel(PASS_REPLY)

    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel(RuntimeError("rate limited")),
            gamma=gamma,
        )
    )

    assert evaluation.passed
    assert evidence_of(evaluation)["judge"] == "judges/gamma"
    assert evidence_of(evaluation)["judge_calls"] == [
        {
            "judge": "judges/beta",
            "status": "error",
            "detail": "RuntimeError: rate limited",
            "usage": None,
        },
        {
            "judge": "judges/gamma",
            "status": "verdict",
            "detail": None,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
                "latency_ms": 250,
                "estimated_cost_usd": 0.001,
            },
        },
    ]


def test_invalid_reply_falls_back_to_the_next_judge_and_keeps_its_usage() -> None:
    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel("Yes, they match."),
            gamma=ScriptedJudgeModel(FAIL_REPLY),
        )
    )

    calls = evidence_of(evaluation)["judge_calls"]

    assert not evaluation.passed
    assert evidence_of(evaluation)["judge"] == "judges/gamma"
    assert isinstance(calls, list)
    assert calls[0] == {
        "judge": "judges/beta",
        "status": "invalid_response",
        "detail": "reply is not JSON",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "latency_ms": 250,
            "estimated_cost_usd": 0.001,
        },
    }


def test_fallback_wraps_around_the_rotation() -> None:
    alpha = ScriptedJudgeModel(PASS_REPLY)

    evaluation = evaluate(
        create_evaluator(
            alpha=alpha,
            beta=ScriptedJudgeModel(RuntimeError("down")),
            gamma=ScriptedJudgeModel("not json"),
        )
    )

    assert evidence_of(evaluation)["judge"] == "judges/alpha"
    assert len(alpha.prompts) == 1


def test_default_expectation_is_assigned_to_beta_first() -> None:
    assert create_rotation().judges_for(create_expected()) == (BETA, GAMMA, ALPHA)


def test_every_judge_failing_raises_judging_error() -> None:
    with pytest.raises(
        SemanticJudgingError,
    ) as error:
        evaluate(
            create_evaluator(
                alpha=ScriptedJudgeModel('{"verdict": "maybe", "reason": "Unsure."}'),
                beta=ScriptedJudgeModel(RuntimeError("down")),
                gamma=ScriptedJudgeModel("not json"),
            )
        )

    assert str(error.value) == (
        "Semantic judging failed with every judge: "
        "judges/beta raised RuntimeError: down; "
        "judges/gamma replied without a usable verdict: reply is not JSON; "
        "judges/alpha replied without a usable verdict: verdict must be 'pass' or 'fail'."
    )


def test_judging_error_is_a_value_error() -> None:
    assert issubclass(SemanticJudgingError, ValueError)


def test_single_judge_rotation_is_valid() -> None:
    judge = ScriptedJudgeModel(PASS_REPLY)

    evaluation = asyncio.run(
        SemanticEvaluator(
            rotation=JudgeRotation(
                entries=(GAMMA,),
            ),
            models={
                GAMMA.identifier: judge,
            },
        ).evaluate(
            create_expected(),
            "It worked.",
        )
    )

    assert evaluation.passed
    assert evidence_of(evaluation)["judge"] == "judges/gamma"


def test_evaluator_rejects_empty_rotation() -> None:
    with pytest.raises(
        ValueError,
        match="^Semantic judging requires at least one judge.$",
    ):
        SemanticEvaluator(
            rotation=JudgeRotation(),
            models={},
        )


def test_evaluator_rejects_judge_without_language_model() -> None:
    with pytest.raises(
        ValueError,
        match="^Judge model judges/beta has no language model.$",
    ):
        SemanticEvaluator(
            rotation=JudgeRotation(
                entries=(
                    ALPHA,
                    BETA,
                ),
            ),
            models={
                ALPHA.identifier: ScriptedJudgeModel(),
            },
        )


def test_judge_prompt_states_expectation_and_both_values() -> None:
    prompt = semantic_judge_prompt(
        ExpectedOutcome(
            description="Summarize the refund policy.",
            value={
                "refund": "30 days",
            },
            comparison=OutcomeComparison.SEMANTIC,
        ),
        "Refunds within a month.",
    )

    assert prompt.text == "\n".join(
        (
            "You are judging whether an actual answer means the same thing as an expected answer.",
            "",
            "Expectation: Summarize the refund policy.",
            "",
            "Expected answer (JSON):",
            "{",
            '  "refund": "30 days"',
            "}",
            "",
            "Actual answer (JSON):",
            '"Refunds within a month."',
            "",
            "Judge meaning, not wording, formatting, or letter case.",
            "Reply with only one JSON object and no other text, in exactly this form:",
            '{"verdict": "pass", "reason": "<one sentence>"}',
            'Use "pass" when the actual answer means the same thing as the expected answer, '
            'and "fail" otherwise.',
        )
    )


def test_every_judge_receives_the_same_prompt() -> None:
    beta = ScriptedJudgeModel(RuntimeError("down"))
    gamma = ScriptedJudgeModel(PASS_REPLY)

    evaluate(
        create_evaluator(
            beta=beta,
            gamma=gamma,
        )
    )

    assert beta.prompts == gamma.prompts
    assert beta.prompts == [semantic_judge_prompt(create_expected(), "It worked.").text]


def test_parse_judge_verdict_accepts_pass_and_fail() -> None:
    assert parse_judge_verdict(PASS_REPLY) == ("pass", "Both say the request succeeded.")
    assert parse_judge_verdict(FAIL_REPLY) == ("fail", "The actual answer reports a failure.")


def test_parse_judge_verdict_tolerates_surrounding_whitespace_and_code_fence() -> None:
    assert parse_judge_verdict(f"\n```json\n{PASS_REPLY}\n```\n") == (
        "pass",
        "Both say the request succeeded.",
    )
    assert parse_judge_verdict(f"```\n{FAIL_REPLY}\n```") == (
        "fail",
        "The actual answer reports a failure.",
    )


def test_parse_judge_verdict_trims_reason() -> None:
    assert parse_judge_verdict('{"verdict": "pass", "reason": "  Same.  "}') == (
        "pass",
        "Same.",
    )


def test_parse_judge_verdict_rejects_unusable_replies() -> None:
    cases = (
        ("Looks right to me.", "reply is not JSON"),
        ('["pass"]', "reply is not a JSON object"),
        ('{"verdict": "PASS", "reason": "Same."}', "verdict must be 'pass' or 'fail'"),
        ('{"reason": "Same."}', "verdict must be 'pass' or 'fail'"),
        ('{"verdict": "pass"}', "reason must be non-empty text"),
        ('{"verdict": "pass", "reason": "   "}', "reason must be non-empty text"),
        ('{"verdict": "pass", "reason": 3}', "reason must be non-empty text"),
    )

    for reply, message in cases:
        with pytest.raises(
            InvalidJudgeResponseError,
        ) as error:
            parse_judge_verdict(reply)

        assert str(error.value) == message


def test_judge_cost_and_call_count_cover_every_recorded_call() -> None:
    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel(
                "not json",
                cost_usd=0.002,
            ),
            gamma=ScriptedJudgeModel(
                PASS_REPLY,
                cost_usd=0.003,
            ),
        )
    )

    assert judge_call_count(evaluation) == 2
    assert judge_calls_cost_usd(evaluation) == pytest.approx(0.005)


def test_errored_judge_call_costs_nothing() -> None:
    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel(RuntimeError("down")),
            gamma=ScriptedJudgeModel(
                PASS_REPLY,
                cost_usd=0.003,
            ),
        )
    )

    assert judge_call_count(evaluation) == 2
    assert judge_calls_cost_usd(evaluation) == pytest.approx(0.003)


def test_non_semantic_evaluation_has_no_judge_calls() -> None:
    evaluation = EvaluationResult(
        evaluator_name="exact-match",
        score=1.0,
        status=EvaluationStatus.PASSED,
        reason="Matched.",
    )

    assert judge_call_count(evaluation) == 0
    assert judge_calls_cost_usd(evaluation) == 0.0


def test_semantic_evaluation_round_trips_through_json() -> None:
    evaluation = evaluate(
        create_evaluator(
            beta=ScriptedJudgeModel(RuntimeError("down")),
            gamma=ScriptedJudgeModel(PASS_REPLY),
        )
    )

    restored = EvaluationResult.model_validate_json(evaluation.model_dump_json())

    assert restored == evaluation
    assert judge_call_count(restored) == 2
