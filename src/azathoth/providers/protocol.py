"""Protocols for language model providers."""

from typing import Protocol

from azathoth.providers.models import (
    ModelResponse,
    Prompt,
)


class LanguageModel(Protocol):
    """A service capable of producing language model completions."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Generate a completion for a rendered prompt."""

        ...
