"""Run language models on Amazon Bedrock, through Converse (ADR 0103).

A prompt of text is one Converse text block, as it always was. A prompt of
parts is a list of blocks in order (ADR 0115): text as `text`, an image as an
`image` block and a PDF as a `document` block, each holding its raw bytes.
Converse's documented limits on images and documents are checked before
anything is sent.
"""

import asyncio
from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from azathoth.inputs import PDF_MEDIA_TYPE
from azathoth.providers.bedrock_client import BedrockClient, BedrockClientError
from azathoth.providers.bedrock_configuration import BEDROCK_PROVIDER
from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.content import prompt_content_bytes
from azathoth.providers.exceptions import ModelExecutionError, UnsupportedModelRequestError
from azathoth.providers.models import ModelPricing, ModelResponse, Prompt, TextPart
from azathoth.providers.registry import LanguageModelRegistry

BLOCKED_STOP_REASONS: Final = frozenset({"guardrail_intervened", "content_filtered"})
"""The stop reasons of a reply that is not an answer."""

TOKENS_PER_MILLION: Final = 1_000_000

BEDROCK_MAX_IMAGES: Final = 20
"""The most images Converse takes in one message."""

BEDROCK_MAX_DOCUMENTS: Final = 5
"""The most documents Converse takes in one message."""

BEDROCK_MAX_IMAGE_BYTES: Final = 3_750_000
"""The largest image Converse takes: 3.75 MB, read as decimal megabytes, the stricter."""

BEDROCK_MAX_DOCUMENT_BYTES: Final = 4_500_000
"""The largest document Converse takes: 4.5 MB, read as decimal megabytes, the stricter."""

BEDROCK_IMAGE_FORMATS: Final[Mapping[str, str]] = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/webp": "webp",
}
"""The Converse `format` of each image media type Azathoth accepts."""


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
            PromptContentError: The prompt shows content whose bytes were not
                given; nothing is sent.
            UnsupportedModelRequestError: The prompt shows more images or
                documents than Converse takes, one larger than it takes, or a
                document with no text beside it; nothing is sent.
            ModelExecutionError: The call failed, its reply is not a Converse
                reply, or a guardrail or content filter stopped it.
        """

        content = bedrock_content(self._model, prompt)

        try:
            raw = await asyncio.to_thread(self._client.converse, self._model, content)
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


def bedrock_content(
    model: str,
    prompt: Prompt,
) -> list[dict[str, object]]:
    """Return the Converse content blocks that send one prompt to one Bedrock model.

    Documents are named `document-<N>` in the order the prompt shows them: a
    neutral name, as Bedrock asks, since a model may read a document's name
    as an instruction.

    Raises:
        PromptContentError: The prompt shows content whose bytes were not
            given.
        UnsupportedModelRequestError: The prompt breaks one of Converse's
            limits on images and documents.
    """

    if not prompt.parts:
        return [{"text": prompt.text}]

    blocks: list[dict[str, object]] = []
    images = 0
    documents = 0

    for part in prompt.parts:
        if isinstance(part, TextPart):
            blocks.append({"text": part.text})
            continue

        shown = part.content
        data = prompt_content_bytes(shown, model=f"{BEDROCK_PROVIDER}/{model}")

        if shown.media_type == PDF_MEDIA_TYPE:
            documents += 1

            if len(data) > BEDROCK_MAX_DOCUMENT_BYTES:
                raise UnsupportedModelRequestError(
                    f"Bedrock model {model!r} is shown documents of at most "
                    f"{BEDROCK_MAX_DOCUMENT_BYTES} bytes; content {shown.digest} is {len(data)}."
                )

            blocks.append(
                {
                    "document": {
                        "format": "pdf",
                        "name": f"document-{documents}",
                        "source": {"bytes": data},
                    }
                }
            )
            continue

        images += 1

        if len(data) > BEDROCK_MAX_IMAGE_BYTES:
            raise UnsupportedModelRequestError(
                f"Bedrock model {model!r} is shown images of at most "
                f"{BEDROCK_MAX_IMAGE_BYTES} bytes; content {shown.digest} is {len(data)}."
            )

        blocks.append(
            {
                "image": {
                    "format": BEDROCK_IMAGE_FORMATS[shown.media_type],
                    "source": {"bytes": data},
                }
            }
        )

    if images > BEDROCK_MAX_IMAGES:
        raise UnsupportedModelRequestError(
            f"Bedrock model {model!r} is shown at most {BEDROCK_MAX_IMAGES} images in one "
            f"prompt; this one shows {images}."
        )

    if documents > BEDROCK_MAX_DOCUMENTS:
        raise UnsupportedModelRequestError(
            f"Bedrock model {model!r} is shown at most {BEDROCK_MAX_DOCUMENTS} documents in "
            f"one prompt; this one shows {documents}."
        )

    if documents and not any("text" in block for block in blocks):
        raise UnsupportedModelRequestError(
            f"Bedrock model {model!r} is shown a document only beside text; this prompt has none."
        )

    return blocks


__all__ = [
    "BEDROCK_IMAGE_FORMATS",
    "BEDROCK_MAX_DOCUMENTS",
    "BEDROCK_MAX_DOCUMENT_BYTES",
    "BEDROCK_MAX_IMAGES",
    "BEDROCK_MAX_IMAGE_BYTES",
    "BLOCKED_STOP_REASONS",
    "BedrockLanguageModel",
    "BedrockModelRegistryLoader",
    "bedrock_content",
]
