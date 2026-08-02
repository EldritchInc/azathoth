"""Runtime registry of executable language model implementations."""

from collections.abc import Mapping

from azathoth.providers.protocol import LanguageModel


class LanguageModelRegistry:
    """Resolve executable language models by provider-qualified identifier."""

    def __init__(
        self,
        models: Mapping[str, LanguageModel] | None = None,
    ) -> None:
        """Create an immutable registry of executable language models."""

        resolved_models = dict(models or {})

        if any(not identifier for identifier in resolved_models):
            raise ValueError("Language model identifiers cannot be empty.")

        self._models = resolved_models

    @property
    def identifiers(self) -> tuple[str, ...]:
        """Return registered identifiers in insertion order."""

        return tuple(self._models)

    def get(self, identifier: str) -> LanguageModel | None:
        """Return the executable model registered for an identifier."""

        return self._models.get(identifier)
