"""OpenRouter language model implementation.

A prompt of text is sent as one user message of text, as it always was. A
prompt of parts is sent as one user message of OpenRouter content parts, in
order (ADR 0115): text as `text`, an image as an `image_url` holding a data
URL, and a PDF as a `file` holding one. A request holding a PDF pins
OpenRouter's PDF engine to `native`, so a model that cannot read files is
never given text another service extracted, at that service's price.
"""

import base64
from time import perf_counter
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from azathoth.inputs import PDF_MEDIA_TYPE
from azathoth.providers.content import prompt_content_bytes
from azathoth.providers.exceptions import ModelExecutionError
from azathoth.providers.models import ModelResponse, Prompt, TextPart
from azathoth.providers.openrouter_models import OpenRouterConfiguration

OPENROUTER_PDF_ENGINE: Final = "native"
"""The engine OpenRouter's file parser reads a PDF with: the model's own (ADR 0115)."""


class _OpenRouterMessage(BaseModel):
    """A message returned by OpenRouter."""

    model_config = ConfigDict(frozen=True)

    content: str


class _OpenRouterChoice(BaseModel):
    """A completion choice returned by OpenRouter."""

    model_config = ConfigDict(frozen=True)

    message: _OpenRouterMessage


class _OpenRouterUsage(BaseModel):
    """Usage accounting returned by OpenRouter."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost: float = Field(default=0.0, ge=0.0)


class _OpenRouterResponse(BaseModel):
    """The subset of an OpenRouter response required by Azathoth."""

    model_config = ConfigDict(frozen=True)

    model: str
    choices: tuple[_OpenRouterChoice, ...] = Field(min_length=1)
    usage: _OpenRouterUsage


class OpenRouterLanguageModel:
    """Execute text completions through OpenRouter."""

    def __init__(
        self,
        configuration: OpenRouterConfiguration,
        model: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not model:
            raise ValueError("OpenRouter model must not be empty.")

        self._configuration = configuration
        self._model = model
        self._transport = transport

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Complete a rendered prompt through OpenRouter.

        Raises:
            PromptContentError: The prompt shows content whose bytes were not
                given; nothing is sent.
            ModelExecutionError: The request failed or its reply is invalid.
        """

        body = openrouter_request(self._model, prompt)
        started_at = perf_counter()

        try:
            response = await self._send(body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelExecutionError(
                f"OpenRouter request for model {self._model!r} failed."
            ) from exc

        latency_ms = round((perf_counter() - started_at) * 1000)

        try:
            payload = _OpenRouterResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ModelExecutionError(
                f"OpenRouter returned an invalid response for model {self._model!r}."
            ) from exc

        return ModelResponse(
            text=payload.choices[0].message.content,
            provider="openrouter",
            model=self._model,
            resolved_model=payload.model,
            prompt_tokens=payload.usage.prompt_tokens,
            completion_tokens=payload.usage.completion_tokens,
            total_tokens=payload.usage.total_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=payload.usage.cost,
        )

    async def _send(
        self,
        body: dict[str, JsonValue],
    ) -> httpx.Response:
        """Send one OpenRouter chat completion request."""

        base_url = f"{self._configuration.base_url.rstrip('/')}/"

        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=self._configuration.timeout_seconds,
            transport=self._transport,
            headers={
                "Authorization": (f"Bearer {self._configuration.api_key.get_secret_value()}"),
            },
        ) as client:
            return await client.post(
                "chat/completions",
                json=body,
            )


def openrouter_request(
    model: str,
    prompt: Prompt,
) -> dict[str, JsonValue]:
    """Return the chat completion request that sends one prompt to one OpenRouter model.

    Raises:
        PromptContentError: The prompt shows content whose bytes were not
            given.
    """

    content: JsonValue = prompt.text
    documents = 0

    if prompt.parts:
        parts: list[JsonValue] = []

        for part in prompt.parts:
            if isinstance(part, TextPart):
                parts.append({"type": "text", "text": part.text})
                continue

            shown = part.content
            data = base64.b64encode(prompt_content_bytes(shown, model=f"openrouter/{model}"))
            url = f"data:{shown.media_type};base64,{data.decode('ascii')}"

            if shown.media_type == PDF_MEDIA_TYPE:
                documents += 1
                parts.append(
                    {
                        "type": "file",
                        "file": {"filename": f"document-{documents}.pdf", "file_data": url},
                    }
                )
            else:
                parts.append({"type": "image_url", "image_url": {"url": url}})

        content = parts

    body: dict[str, JsonValue] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }

    if documents:
        body["plugins"] = [{"id": "file-parser", "pdf": {"engine": OPENROUTER_PDF_ENGINE}}]

    return body
