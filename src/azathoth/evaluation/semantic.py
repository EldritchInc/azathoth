"""Semantic outcome evaluation by a rotation of language-model judges."""

import json
from collections.abc import Mapping

from pydantic import JsonValue

from azathoth.evaluation.judges import (
    JudgeEntry,
    JudgeRotation,
)
from azathoth.evaluation.models import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
)
from azathoth.evaluation.protocols import EvaluatorMetadata
from azathoth.providers.models import (
    ModelResponse,
    Prompt,
)
from azathoth.providers.protocol import LanguageModel

SEMANTIC_EVALUATOR_NAME = "semantic-judge"

SEMANTIC_EVALUATOR_VERSION = "1.0.0"

PASS_VERDICT = "pass"

FAIL_VERDICT = "fail"


class SemanticJudgingError(ValueError):
    """Raised when no judge in the rotation returned a usable verdict.

    A judging failure is an infrastructure failure of Azathoth itself, not a
    failure of the judged candidate, so it is never recorded as a failed case.
    """


class InvalidJudgeResponseError(ValueError):
    """Raised when a judge's reply is not a usable verdict."""


class SemanticEvaluator:
    """Judge whether an actual value means what the expected value means.

    Each expectation is judged first by the judge the rotation assigns to it,
    so every candidate judged against the same benchmark case meets the same
    judge. A judge that fails or replies without a usable verdict is followed
    by the next judge in rotation order. Every judge call, successful or not,
    is recorded in the evaluation evidence with its usage, because judging is
    Azathoth's own cost rather than the candidate's.
    """

    def __init__(
        self,
        *,
        rotation: JudgeRotation,
        models: Mapping[str, LanguageModel],
    ) -> None:
        """Bind every judge in the rotation to its language model.

        Raises:
            ValueError: The rotation is empty, or a judge has no language
                model.
        """

        if not rotation.entries:
            raise ValueError("Semantic judging requires at least one judge.")

        for identifier in rotation.identifiers:
            if identifier not in models:
                raise ValueError(f"Judge model {identifier} has no language model.")

        self._rotation = rotation
        self._models = dict(models)
        self._metadata = EvaluatorMetadata(
            name=SEMANTIC_EVALUATOR_NAME,
            description="Judge semantic equivalence with a rotation of language models.",
            version=SEMANTIC_EVALUATOR_VERSION,
        )

    @property
    def metadata(self) -> EvaluatorMetadata:
        """Return stable identifying metadata for this evaluator."""

        return self._metadata

    @property
    def rotation(self) -> JudgeRotation:
        """Return the judges this evaluator assigns expectations to."""

        return self._rotation

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        """Judge one actual value with the judges assigned to its expectation.

        Raises:
            SemanticJudgingError: Every judge failed or replied without a
                usable verdict.
        """

        prompt = semantic_judge_prompt(
            expected,
            actual,
        )

        calls: list[JsonValue] = []
        failures: list[str] = []

        for judge in self._rotation.judges_for(expected):
            try:
                response = await self._models[judge.identifier].complete(prompt)
            except Exception as exc:
                calls.append(
                    _judge_call(
                        judge,
                        status="error",
                        detail=f"{type(exc).__name__}: {exc}",
                        response=None,
                    )
                )
                failures.append(f"{judge.identifier} raised {type(exc).__name__}: {exc}")
                continue

            try:
                verdict, reason = parse_judge_verdict(response.text)
            except InvalidJudgeResponseError as exc:
                calls.append(
                    _judge_call(
                        judge,
                        status="invalid_response",
                        detail=str(exc),
                        response=response,
                    )
                )
                failures.append(f"{judge.identifier} replied without a usable verdict: {exc}")
                continue

            calls.append(
                _judge_call(
                    judge,
                    status="verdict",
                    detail=None,
                    response=response,
                )
            )

            return _result(
                expected=expected,
                actual=actual,
                judge=judge,
                verdict=verdict,
                reason=reason,
                calls=calls,
            )

        raise SemanticJudgingError(
            "Semantic judging failed with every judge: " + "; ".join(failures) + "."
        )


def semantic_judge_prompt(
    expected: ExpectedOutcome,
    actual: JsonValue,
) -> Prompt:
    """Return the prompt asking a judge whether two values mean the same thing."""

    return Prompt(
        text="\n".join(
            (
                "You are judging whether an actual answer means the same thing as an "
                "expected answer.",
                "",
                f"Expectation: {expected.description}",
                "",
                "Expected answer (JSON):",
                _json_text(expected.value),
                "",
                "Actual answer (JSON):",
                _json_text(actual),
                "",
                "Judge meaning, not wording, formatting, or letter case.",
                "Reply with only one JSON object and no other text, in exactly this form:",
                '{"verdict": "pass", "reason": "<one sentence>"}',
                'Use "pass" when the actual answer means the same thing as the expected '
                'answer, and "fail" otherwise.',
            )
        ),
    )


def parse_judge_verdict(
    text: str,
) -> tuple[str, str]:
    """Return the verdict and reason from one judge reply.

    The reply must be one JSON object whose `verdict` is `pass` or `fail` and
    whose `reason` is non-empty text. A single surrounding Markdown code fence
    is tolerated.

    Raises:
        InvalidJudgeResponseError: The reply is not a usable verdict.
    """

    stripped = _strip_code_fence(text.strip())

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise InvalidJudgeResponseError("reply is not JSON") from exc

    if not isinstance(payload, dict):
        raise InvalidJudgeResponseError("reply is not a JSON object")

    verdict = payload.get("verdict")

    if verdict not in (PASS_VERDICT, FAIL_VERDICT):
        raise InvalidJudgeResponseError("verdict must be 'pass' or 'fail'")

    reason = payload.get("reason")

    if not isinstance(reason, str) or not reason.strip():
        raise InvalidJudgeResponseError("reason must be non-empty text")

    return verdict, reason.strip()


def judge_calls_cost_usd(
    evaluation: EvaluationResult,
) -> float:
    """Return the total judge cost recorded in one evaluation's evidence.

    Calls that raised before replying recorded no usage and cost nothing.
    """

    total = 0.0

    for usage in _judge_usages(evaluation):
        cost = usage.get("estimated_cost_usd")

        if isinstance(cost, int | float) and not isinstance(cost, bool):
            total += float(cost)

    return total


def judge_call_count(
    evaluation: EvaluationResult,
) -> int:
    """Return how many judge calls one evaluation's evidence records."""

    count = 0

    for item in _judge_call_evidence(evaluation):
        if isinstance(item.value, list):
            count += len(item.value)

    return count


def _judge_call_evidence(
    evaluation: EvaluationResult,
) -> tuple[EvaluationEvidence, ...]:
    """Return the judge-call evidence items of one evaluation."""

    return tuple(
        item
        for item in evaluation.evidence
        if item.label == "judge_calls" and isinstance(item.value, list)
    )


def _judge_usages(
    evaluation: EvaluationResult,
) -> tuple[dict[str, JsonValue], ...]:
    """Return the usage of every recorded judge call that has one."""

    usages: list[dict[str, JsonValue]] = []

    for item in _judge_call_evidence(evaluation):
        if not isinstance(item.value, list):
            continue

        for call in item.value:
            if isinstance(call, dict):
                usage = call.get("usage")

                if isinstance(usage, dict):
                    usages.append(usage)

    return tuple(usages)


def _result(
    *,
    expected: ExpectedOutcome,
    actual: JsonValue,
    judge: JudgeEntry,
    verdict: str,
    reason: str,
    calls: list[JsonValue],
) -> EvaluationResult:
    """Return the evaluation for one usable verdict."""

    passed = verdict == PASS_VERDICT

    relation = "equivalent to" if passed else "not equivalent to"

    return EvaluationResult(
        evaluator_name=SEMANTIC_EVALUATOR_NAME,
        evaluator_version=SEMANTIC_EVALUATOR_VERSION,
        score=1.0 if passed else 0.0,
        threshold=1.0,
        status=EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED,
        reason=(
            f"Judge {judge.identifier} found the actual value {relation} the expected "
            f"value: {reason}"
        ),
        evidence=(
            EvaluationEvidence(
                label="expected",
                value=expected.value,
            ),
            EvaluationEvidence(
                label="actual",
                value=actual,
            ),
            EvaluationEvidence(
                label="judge",
                value=judge.identifier,
            ),
            EvaluationEvidence(
                label="verdict",
                value=verdict,
            ),
            EvaluationEvidence(
                label="judge_reason",
                value=reason,
            ),
            EvaluationEvidence(
                label="judge_calls",
                value=calls,
            ),
        ),
    )


def _judge_call(
    judge: JudgeEntry,
    *,
    status: str,
    detail: str | None,
    response: ModelResponse | None,
) -> JsonValue:
    """Return the evidence record of one judge call."""

    return {
        "judge": judge.identifier,
        "status": status,
        "detail": detail,
        "usage": (
            {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
                "estimated_cost_usd": response.estimated_cost_usd,
            }
            if response is not None
            else None
        ),
    }


def _json_text(
    value: JsonValue,
) -> str:
    """Render one JSON value for a judge prompt."""

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )


def _strip_code_fence(
    text: str,
) -> str:
    """Remove one surrounding Markdown code fence, if present."""

    if not (text.startswith("```") and text.endswith("```")):
        return text

    body = text[3:-3]

    first_newline = body.find("\n")

    if first_newline != -1 and body[:first_newline].strip().isalpha():
        body = body[first_newline + 1 :]

    return body.strip()
