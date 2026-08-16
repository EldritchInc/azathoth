"""OpenRouter language model implementation."""

from time import perf_counter

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from azathoth.providers.exceptions import ModelExecutionError
from azathoth.providers.models import ModelResponse, Prompt
from azathoth.providers.openrouter_models import OpenRouterConfiguration


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
        """Complete a rendered prompt through OpenRouter."""

        started_at = perf_counter()

        try:
            response = await self._send(prompt)
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
            model=payload.model,
            prompt_tokens=payload.usage.prompt_tokens,
            completion_tokens=payload.usage.completion_tokens,
            total_tokens=payload.usage.total_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=payload.usage.cost,
        )

    async def _send(
        self,
        prompt: Prompt,
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
                json={
                    "model": self._model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt.text,
                        },
                    ],
                },
            )
