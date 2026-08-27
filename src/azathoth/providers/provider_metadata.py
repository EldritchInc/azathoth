"""Translate current provider model state into runtime model metadata."""

from azathoth.providers.models import ModelMetadata
from azathoth.providers.provider_models import ProviderModel


def model_metadata_from_provider_model(
    model: ProviderModel,
) -> ModelMetadata:
    """Derive runtime metadata from current provider-reported model state."""

    return ModelMetadata(
        provider=model.provider,
        model=model.model,
        display_name=model.display_name,
        input_modalities=model.input_modalities,
        output_modalities=model.output_modalities,
        capabilities=model.capabilities,
        context_window_tokens=model.context_window_tokens,
        maximum_output_tokens=model.maximum_output_tokens,
        pricing=model.pricing,
    )
