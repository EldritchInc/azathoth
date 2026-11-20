"""Tests that every model call's cost says how it is known (ADR 0132)."""

import asyncio
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from azathoth.costs import BILLING_PROVIDERS, COST_BASES, cost_basis_of
from azathoth.prompting.execution import execute_prompt
from azathoth.providers import ModelResponse, OpenRouterLanguageModel, Prompt
from azathoth.strategies import StrategyExecutionMetrics
from tests.providers.test_openrouter import create_configuration, create_response


def response(**changes: Any) -> ModelResponse:
    """Return one model's reply, changed as given."""

    fields: dict[str, Any] = {
        "text": "done",
        "provider": "openrouter",
        "model": "acme/small",
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
        "latency_ms": 15,
        "estimated_cost_usd": 0.0001,
        "cost_basis": "billed",
    }
    fields.update(changes)

    return ModelResponse.model_validate(fields)


class ReplyingModel:
    """A model that replies with one response."""

    def __init__(self, reply: ModelResponse) -> None:
        self._reply = reply

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Return the reply, whatever the prompt."""

        del prompt

        return self._reply


# The basis


def test_a_cost_is_billed_or_estimated() -> None:
    assert COST_BASES == ("billed", "estimated")
    assert frozenset({"openrouter"}) == BILLING_PROVIDERS


def test_a_recorded_basis_is_the_basis() -> None:
    assert cost_basis_of("bedrock", 0.5, "billed") == "billed"
    assert cost_basis_of("openrouter", 0.5, "estimated") == "estimated"


def test_a_call_with_no_cost_has_no_basis() -> None:
    assert cost_basis_of("openrouter", None, None) is None
    assert cost_basis_of("bedrock", None, None) is None


@pytest.mark.parametrize(
    ("provider", "basis"),
    [("openrouter", "billed"), ("bedrock", "estimated"), ("deterministic", "estimated")],
)
def test_a_cost_recorded_before_1_5_is_read_from_its_provider(provider: str, basis: str) -> None:
    assert cost_basis_of(provider, 0.25, None) == basis


def test_a_cost_with_no_basis_and_no_provider_has_none() -> None:
    assert cost_basis_of(None, 0.0, None) is None


# A model's reply


def test_a_reply_says_how_its_cost_is_known() -> None:
    assert response().cost_basis == "billed"
    assert response(cost_basis="estimated").cost_basis == "estimated"


def test_a_reply_recorded_before_1_5_has_no_basis_of_its_own() -> None:
    fields = response().model_dump()
    del fields["cost_basis"]

    assert ModelResponse.model_validate(fields).cost_basis is None


def test_an_unpriced_reply_has_no_basis() -> None:
    with pytest.raises(ValidationError, match="no cost basis"):
        response(estimated_cost_usd=None, cost_basis="billed")

    assert response(estimated_cost_usd=None, cost_basis=None).cost_basis is None


def test_a_basis_is_only_billed_or_estimated() -> None:
    with pytest.raises(ValidationError):
        response(cost_basis="guessed")


def test_an_openrouter_reply_with_no_cost_is_unpriced_never_free() -> None:
    reply = create_response()
    del reply["usage"]["cost"]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply, request=request)

    model = OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )
    completed = asyncio.run(model.complete(Prompt(text="Classify this.")))

    assert completed.estimated_cost_usd is None
    assert completed.cost_basis is None


# A step's metrics


def test_a_prompt_steps_metrics_keep_its_replys_basis() -> None:
    outcome = asyncio.run(
        execute_prompt(
            prompt=Prompt(text="Classify this."),
            language_model=ReplyingModel(response(cost_basis="estimated")),
            model_binding=None,
        )
    )

    assert outcome.metrics is not None
    assert outcome.metrics.cost_basis == "estimated"
    assert outcome.metrics.known_cost_basis == "estimated"


def test_metrics_refuse_a_basis_with_no_cost() -> None:
    with pytest.raises(ValidationError, match="no cost basis"):
        StrategyExecutionMetrics(provider="openrouter", cost_basis="billed")


def test_metrics_keep_their_basis_through_storage() -> None:
    metrics = StrategyExecutionMetrics(
        provider="bedrock",
        model="amazon.nova-pro-v1:0",
        estimated_cost_usd=0.002,
        cost_basis="estimated",
    )

    assert StrategyExecutionMetrics.model_validate_json(metrics.model_dump_json()) == metrics


@pytest.mark.parametrize(
    ("provider", "basis"),
    [("openrouter", "billed"), ("bedrock", "estimated")],
)
def test_metrics_stored_before_1_5_read_their_basis_from_their_provider(
    provider: str, basis: str
) -> None:
    stored = f'{{"provider": "{provider}", "model": "m", "estimated_cost_usd": 0.01}}'
    metrics = StrategyExecutionMetrics.model_validate_json(stored)

    assert metrics.cost_basis is None
    assert metrics.known_cost_basis == basis


def test_a_tool_steps_metrics_name_no_provider_and_so_no_basis() -> None:
    assert StrategyExecutionMetrics(estimated_cost_usd=0.0).known_cost_basis is None
