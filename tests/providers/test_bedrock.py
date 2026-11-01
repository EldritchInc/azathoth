"""Tests for running language models on Bedrock through Converse (ADR 0103)."""

import asyncio
from collections.abc import Mapping

import pytest

from azathoth.providers import (
    BLOCKED_STOP_REASONS,
    BedrockClientError,
    BedrockLanguageModel,
    BedrockModelRegistryLoader,
    LanguageModel,
    ModelCatalog,
    ModelExecutionError,
    ModelExecutor,
    ModelMetadata,
    ModelPricing,
    ModelRequest,
    ModelResponse,
    Prompt,
)
from tests.providers.fake_bedrock import FakeBedrockClient

NOVA_PRO = "amazon.nova-pro-v1:0"

US_CLAUDE = "us.anthropic.claude-sonnet-4-20250514-v1:0"

PRICE = ModelPricing(
    input_usd_per_million_tokens=0.8,
    output_usd_per_million_tokens=3.2,
)

PROMPT = Prompt(text="How many words are in 'the old ones wait'?")


def converse_reply(
    *content: Mapping[str, object],
    stop_reason: str = "end_turn",
    input_tokens: int = 1_000,
    output_tokens: int = 250,
    latency_ms: int = 412,
) -> dict[str, object]:
    """Return one Converse reply, as AWS gives it."""

    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": list(content) or [{"text": "4"}],
            },
        },
        "stopReason": stop_reason,
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
        },
        "metrics": {"latencyMs": latency_ms},
    }


def complete(
    client: FakeBedrockClient,
    *,
    model: str = NOVA_PRO,
    pricing: ModelPricing | None = PRICE,
) -> ModelResponse:
    """Complete the prompt with one model over a fake client."""

    return asyncio.run(BedrockLanguageModel(client, model, pricing=pricing).complete(PROMPT))


# Completing


def test_a_bedrock_model_is_a_language_model() -> None:
    language_model: LanguageModel = BedrockLanguageModel(FakeBedrockClient(), NOVA_PRO)

    assert language_model is not None


def test_the_prompt_is_sent_to_the_model_through_converse() -> None:
    client = FakeBedrockClient(replies={NOVA_PRO: [converse_reply()]})

    complete(client)

    assert client.calls == [("converse", NOVA_PRO, PROMPT.text)]


def test_a_reply_becomes_provider_neutral_evidence() -> None:
    client = FakeBedrockClient(replies={NOVA_PRO: [converse_reply()]})

    assert complete(client) == ModelResponse(
        text="4",
        provider="bedrock",
        model=NOVA_PRO,
        resolved_model=None,
        prompt_tokens=1_000,
        completion_tokens=250,
        total_tokens=1_250,
        latency_ms=412,
        estimated_cost_usd=(1_000 * 0.8 + 250 * 3.2) / 1_000_000,
    )


def test_an_inference_profile_is_called_by_its_profile_id() -> None:
    client = FakeBedrockClient(replies={US_CLAUDE: [converse_reply()]})

    response = complete(client, model=US_CLAUDE)

    assert response.model == US_CLAUDE
    assert client.calls == [("converse", US_CLAUDE, PROMPT.text)]


def test_the_answer_is_the_text_blocks_joined_in_order() -> None:
    client = FakeBedrockClient(
        replies={
            NOVA_PRO: [
                converse_reply(
                    {"reasoningContent": {"reasoningText": {"text": "Count them."}}},
                    {"text": '{"count": '},
                    {"text": "4}"},
                ),
            ],
        },
    )

    assert complete(client).text == '{"count": 4}'


def test_a_reply_without_text_is_an_empty_answer() -> None:
    client = FakeBedrockClient(
        replies={
            NOVA_PRO: [converse_reply({"reasoningContent": {"reasoningText": {"text": "…"}}})]
        },
    )

    assert complete(client).text == ""


def test_the_total_is_the_sum_of_input_and_output_tokens() -> None:
    reply = converse_reply(input_tokens=10, output_tokens=5)
    usage = reply["usage"]

    assert isinstance(usage, dict)

    usage["totalTokens"] = 99
    usage["cacheReadInputTokens"] = 84

    response = complete(FakeBedrockClient(replies={NOVA_PRO: [reply]}))

    assert (response.prompt_tokens, response.completion_tokens, response.total_tokens) == (
        10,
        5,
        15,
    )


def test_a_reply_that_stopped_at_its_token_limit_is_an_answer() -> None:
    client = FakeBedrockClient(
        replies={NOVA_PRO: [converse_reply({"text": "The old"}, stop_reason="max_tokens")]},
    )

    assert complete(client).text == "The old"


# Cost


def test_an_unpriced_model_has_an_unknown_cost_never_a_free_one() -> None:
    client = FakeBedrockClient(replies={NOVA_PRO: [converse_reply()]})

    assert complete(client, pricing=None).estimated_cost_usd is None


def test_a_call_with_no_tokens_costs_nothing_at_any_price() -> None:
    client = FakeBedrockClient(
        replies={NOVA_PRO: [converse_reply(input_tokens=0, output_tokens=0)]},
    )

    assert complete(client).estimated_cost_usd == 0.0


# Failures


@pytest.mark.parametrize("stop_reason", sorted(BLOCKED_STOP_REASONS))
def test_a_reply_a_guardrail_or_filter_stopped_is_a_failed_call(
    stop_reason: str,
) -> None:
    client = FakeBedrockClient(
        replies={NOVA_PRO: [converse_reply({"text": "Sorry."}, stop_reason=stop_reason)]},
    )

    with pytest.raises(ModelExecutionError) as raised:
        complete(client)

    assert str(raised.value) == (
        f"Bedrock stopped model {NOVA_PRO!r} without an answer: {stop_reason}."
    )


def test_the_blocked_stop_reasons_are_the_guardrail_and_the_content_filter() -> None:
    assert frozenset({"guardrail_intervened", "content_filtered"}) == BLOCKED_STOP_REASONS


def test_an_aws_error_is_a_failed_call_naming_the_model_and_awss_code() -> None:
    client = FakeBedrockClient(
        replies={
            NOVA_PRO: [BedrockClientError("ThrottlingException", "Too many requests.")],
        },
    )

    with pytest.raises(ModelExecutionError) as raised:
        complete(client)

    assert str(raised.value) == (
        f"Bedrock request for model {NOVA_PRO!r} failed: ThrottlingException: Too many requests."
    )
    assert isinstance(raised.value.__cause__, BedrockClientError)


def test_a_reply_that_is_not_a_converse_reply_is_a_failed_call() -> None:
    reply = converse_reply()
    del reply["usage"]

    with pytest.raises(ModelExecutionError) as raised:
        complete(FakeBedrockClient(replies={NOVA_PRO: [reply]}))

    assert str(raised.value) == f"Bedrock returned an invalid response for model {NOVA_PRO!r}."


def test_an_empty_model_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        BedrockLanguageModel(FakeBedrockClient(), "")


def test_the_executor_runs_a_bedrock_model() -> None:
    client = FakeBedrockClient(replies={NOVA_PRO: [converse_reply()]})
    model = BedrockLanguageModel(client, NOVA_PRO, pricing=PRICE)

    response = asyncio.run(ModelExecutor().execute(ModelRequest(prompt=PROMPT), model))

    assert response.text == "4"


# The registry


def catalog() -> ModelCatalog:
    """Return a catalog with two Bedrock models, one priced, and one OpenRouter model."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="bedrock", model=NOVA_PRO, display_name="Nova Pro", pricing=PRICE
            ),
            ModelMetadata(provider="bedrock", model=US_CLAUDE, display_name="US Claude"),
            ModelMetadata(provider="openrouter", model="example/model", display_name="Example"),
        ),
    )


def test_the_registry_holds_every_bedrock_model_of_the_catalog_and_no_other() -> None:
    registry = BedrockModelRegistryLoader(FakeBedrockClient()).load_registry(catalog())

    assert registry.identifiers == (f"bedrock/{NOVA_PRO}", f"bedrock/{US_CLAUDE}")
    assert registry.get("openrouter/example/model") is None


def test_each_registered_model_is_priced_from_the_catalog() -> None:
    client = FakeBedrockClient(
        replies={NOVA_PRO: [converse_reply()], US_CLAUDE: [converse_reply()]},
    )
    registry = BedrockModelRegistryLoader(client).load_registry(catalog())

    nova_pro = registry.get(f"bedrock/{NOVA_PRO}")
    us_claude = registry.get(f"bedrock/{US_CLAUDE}")

    assert nova_pro is not None
    assert us_claude is not None
    assert asyncio.run(nova_pro.complete(PROMPT)).estimated_cost_usd == pytest.approx(0.0016)
    assert asyncio.run(us_claude.complete(PROMPT)).estimated_cost_usd is None
    assert [call[1] for call in client.calls] == [NOVA_PRO, US_CLAUDE]
