"""Language model provider abstractions."""

from azathoth.providers.models import (
    ModelResponse,
    Prompt,
)
from azathoth.providers.protocol import LanguageModel

__all__ = [
    "LanguageModel",
    "ModelResponse",
    "Prompt",
]
