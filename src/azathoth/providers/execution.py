"""Provider-neutral execution of durable model requests."""

from azathoth.providers.exceptions import UnsupportedModelRequestError
from azathoth.providers.models import ModelRequest, ModelResponse
from azathoth.providers.protocol import LanguageModel


class ModelExecutor:
    """Execute durable requests through existing language model providers."""

    async def execute(
        self,
        request: ModelRequest,
        language_model: LanguageModel,
    ) -> ModelResponse:
        """Execute a model request through a language model."""

        self._validate_request(request)

        return await language_model.complete(request.prompt)

    @staticmethod
    def _validate_request(
        request: ModelRequest,
    ) -> None:
        """Reject request controls unsupported by the current provider boundary."""

        unsupported_controls: list[str] = []

        if request.temperature is not None:
            unsupported_controls.append("temperature")

        if request.max_output_tokens is not None:
            unsupported_controls.append("max_output_tokens")

        if unsupported_controls:
            controls = ", ".join(unsupported_controls)
            raise UnsupportedModelRequestError(
                f"Model request controls are not yet supported: {controls}."
            )
