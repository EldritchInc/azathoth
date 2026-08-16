"""Deterministic language model implementation."""

from azathoth.providers.models import ModelResponse, Prompt


class DeterministicLanguageModel:
    """Return deterministic responses for testing and local execution."""

    def __init__(
        self,
        *,
        provider: str = "deterministic",
        model: str = "deterministic",
        response_text: str = "deterministic response",
    ) -> None:
        self._provider = provider
        self._model = model
        self._response_text = response_text

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a deterministic completion."""

        prompt_tokens = len(prompt.text.split())
        completion_tokens = len(self._response_text.split())

        return ModelResponse(
            text=self._response_text,
            provider=self._provider,
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )
