"""Protocols implemented by language model providers."""

from typing import Protocol

from azathoth.providers.models import ModelResponse, Prompt


class LanguageModel(Protocol):
    """A service capable of completing language model prompts."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Complete a rendered prompt."""

        ...
