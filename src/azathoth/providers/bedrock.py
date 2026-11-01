"""Run language models on Amazon Bedrock, through Converse (ADR 0103)."""

import asyncio
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from azathoth.providers.bedrock_client import BedrockClient, BedrockClientError
from azathoth.providers.bedrock_configuration import BEDROCK_PROVIDER
from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.exceptions import ModelExecutionError
from azathoth.providers.models import ModelPricing, ModelResponse, Prompt
from azathoth.providers.registry import LanguageModelRegistry

BLOCKED_STOP_REASONS: Final = frozenset({"guardrail_intervened", "content_filtered"})
"""The stop reasons of a reply that is not an answer."""

TOKENS_PER_MILLION: Final = 1_000_000


class _ContentBlock(BaseModel):
    """One block of a reply's message; only text blocks are part of the answer."""

    model_config = ConfigDict(frozen=True)

    text: str | None = None


class _Message(BaseModel):
    """The reply's message."""

    model_config = ConfigDict(frozen=True)

    content: tuple[_ContentBlock, ...] = ()


class _Output(BaseModel):
    """The reply's output."""

    model_config = ConfigDict(frozen=True)

    message: _Message


class _Usage(BaseModel):
    """The tokens a call used."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(alias="inputTokens", ge=0)
    output_tokens: int = Field(alias="outputTokens", ge=0)


class _Metrics(BaseModel):
    """What Bedrock measured of a call."""

    model_config = ConfigDict(frozen=True)

    latency_ms: int = Field(alias="latencyMs", ge=0)


class _ConverseReply(BaseModel):
    """The part of a Converse reply Azathoth reads."""

    model_config = ConfigDict(frozen=True)

    output: _Output
    stop_reason: str = Field(alias="stopReason")
    usage: _Usage
    metrics: _Metrics


class BedrockLanguageModel:
    """Complete prompts with one Bedrock model, or inference profile, through Converse.

    The prompt is sent as one user message, with no inference settings. The
    answer is the reply's text blocks, joined. Its cost is its tokens at the
    model's price, or unknown when the model is not priced.
    """

    def __init__(
        self,
        client: BedrockClient,
        model: str,
        *,
        pricing: ModelPricing | None = None,
    ) -> None:
        if not model:
            raise ValueError("Bedrock model must not be empty.")

        self._client = client
        self._model = model
        self._pricing = pricing

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Complete a rendered prompt through Converse.

        Raises:
            ModelExecutionError: The call failed, its reply is not a Converse
                reply, or a guardrail or content filter stopped it.
        """

        try:
            raw = await asyncio.to_thread(self._client.converse, self._model, prompt.text)
        except BedrockClientError as exc:
            detail = str(exc).rstrip(".")

            raise ModelExecutionError(
                f"Bedrock request for model {self._model!r} failed: {detail}."
            ) from exc

        try:
            reply = _ConverseReply.model_validate(raw)
        except ValidationError as exc:
            raise ModelExecutionError(
                f"Bedrock returned an invalid response for model {self._model!r}."
            ) from exc

        if reply.stop_reason in BLOCKED_STOP_REASONS:
            raise ModelExecutionError(
                f"Bedrock stopped model {self._model!r} without an answer: {reply.stop_reason}."
            )

        input_tokens = reply.usage.input_tokens
        output_tokens = reply.usage.output_tokens

        return ModelResponse(
            text="".join(
                block.text for block in reply.output.message.content if block.text is not None
            ),
            provider=BEDROCK_PROVIDER,
            model=self._model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=reply.metrics.latency_ms,
            estimated_cost_usd=self._cost(input_tokens, output_tokens),
        )

    def _cost(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> float | None:
        """Return a call's cost at the model's price, or None when it is not priced."""

        if self._pricing is None:
            return None

        return (
            input_tokens * self._pricing.input_usd_per_million_tokens
            + output_tokens * self._pricing.output_usd_per_million_tokens
        ) / TOKENS_PER_MILLION


class BedrockModelRegistryLoader:
    """Build executable Bedrock models for the Bedrock models of a catalog."""

    def __init__(
        self,
        client: BedrockClient,
    ) -> None:
        self._client = client

    def load_registry(
        self,
        catalog: ModelCatalog,
    ) -> LanguageModelRegistry:
        """Build one model for every Bedrock model in the catalog, at its catalog price."""

        models = {
            metadata.identifier: BedrockLanguageModel(
                self._client,
                metadata.model,
                pricing=metadata.pricing,
            )
            for metadata in catalog.models_for_provider(BEDROCK_PROVIDER)
        }

        return LanguageModelRegistry(models=models)


__all__ = [
    "BLOCKED_STOP_REASONS",
    "BedrockLanguageModel",
    "BedrockModelRegistryLoader",
]
