"""Tests for workflow prompt steps that reply in JSON."""

import asyncio
from uuid import UUID

from azathoth.context import Context
from azathoth.prompting import (
    ContextPromptStrategy,
    PromptOutputFormat,
    PromptTemplate,
)
from azathoth.providers import ModelResponse, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
)

WORKFLOW_ID = UUID("c6000000-0000-4000-8000-000000000001")

STEP_ID = UUID("c6000000-0000-4000-8000-000000000011")

STRATEGY_ID = UUID("c6000000-0000-4000-8000-000000000021")

CHARACTERS_REPLY = '```json\n{"characters": [{"name": "Ada"}, {"name": "Grace"}]}\n```'


class ScriptedLanguageModel:
    """Reply with each scripted text in turn."""

    def __init__(
        self,
        *replies: str,
    ) -> None:
        self._replies = list(replies)
        self.calls = 0

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return the next scripted reply."""

        reply = self._replies[self.calls]
        self.calls += 1

        return ModelResponse(
            text=reply,
            provider="test",
            model="scripted",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )


def plan_candidate(
    model: ScriptedLanguageModel,
    *,
    max_attempts: int = 1,
) -> WorkflowCandidate:
    """Create a one-step workflow reading characters out of a JSON reply."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Plan characters",
            description="Read structured characters from a model reply.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=ContextPromptStrategy(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Plan characters",
                        description="Plan the novel's characters.",
                        version="1.0.0",
                    ),
                    template=PromptTemplate(text="Plan the characters."),
                    language_model=model,
                    output_format=PromptOutputFormat.JSON,
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="first_character",
                        path=("characters", 0, "name"),
                    ),
                ),
                retry_policy=WorkflowRetryPolicy(max_attempts=max_attempts),
            ),
        ),
    )


def test_output_bindings_read_fields_of_a_json_reply() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            plan_candidate(ScriptedLanguageModel(CHARACTERS_REPLY)),
            Context(),
        )
    )

    step = run.steps[0]

    assert step.status == WorkflowStepStatus.EXECUTED
    assert tuple((value.name, value.value) for value in step.values) == (
        ("first_character", "Ada"),
    )


def test_invalid_json_reply_is_a_failed_attempt_that_is_retried() -> None:
    model = ScriptedLanguageModel("Here are your characters!", CHARACTERS_REPLY)

    run = asyncio.run(
        WorkflowRunner().run(
            plan_candidate(model, max_attempts=2),
            Context(),
        )
    )

    step = run.steps[0]

    assert model.calls == 2
    assert step.status == WorkflowStepStatus.EXECUTED
    assert len(step.attempts) == 2

    failure = step.attempts[0].failure

    assert failure is not None
    assert failure.exception_type == "PromptOutputFormatError"
    assert failure.message == (
        "Prompt strategy 'Plan characters' replied with invalid JSON: Expecting value."
    )
