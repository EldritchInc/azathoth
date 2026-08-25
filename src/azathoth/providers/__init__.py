"""Language model provider abstractions."""

from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.catalog_loader import ModelCatalogLoader
from azathoth.providers.deterministic import DeterministicLanguageModel
from azathoth.providers.exceptions import (
    ModelExecutionError,
    UnsupportedModelRequestError,
)
from azathoth.providers.execution import ModelExecutor
from azathoth.providers.memory_repository import (
    InMemoryModelRepository,
    require_model_repository,
)
from azathoth.providers.models import (
    ModelCapability,
    ModelMetadata,
    ModelModality,
    ModelPricing,
    ModelRequest,
    ModelResponse,
    Prompt,
)
from azathoth.providers.openrouter import OpenRouterLanguageModel
from azathoth.providers.openrouter_models import OpenRouterConfiguration
from azathoth.providers.openrouter_registry import (
    OpenRouterModelRegistryLoader,
)
from azathoth.providers.protocol import LanguageModel
from azathoth.providers.provider_models import (
    ProviderModel,
    ProviderModelObservation,
)
from azathoth.providers.query import ModelQuery
from azathoth.providers.registry import LanguageModelRegistry
from azathoth.providers.repository import ModelRepository
from azathoth.providers.requirements import ModelRequirements
from azathoth.providers.sqlite_repository import SQLiteModelRepository

__all__ = [
    "DeterministicLanguageModel",
    "InMemoryModelRepository",
    "LanguageModel",
    "LanguageModelRegistry",
    "ModelCapability",
    "ModelCatalog",
    "ModelCatalogLoader",
    "ModelExecutionError",
    "ModelExecutor",
    "ModelMetadata",
    "ModelModality",
    "ModelPricing",
    "ModelQuery",
    "ModelRequest",
    "ModelRepository",
    "ModelRequirements",
    "ModelResponse",
    "OpenRouterConfiguration",
    "OpenRouterLanguageModel",
    "OpenRouterModelRegistryLoader",
    "Prompt",
    "ProviderModel",
    "ProviderModelObservation",
    "SQLiteModelRepository",
    "UnsupportedModelRequestError",
    "require_model_repository",
]
