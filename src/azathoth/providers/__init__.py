"""Language model provider abstractions."""

from azathoth.providers.bedrock import (
    BLOCKED_STOP_REASONS,
    BedrockLanguageModel,
    BedrockModelRegistryLoader,
)
from azathoth.providers.bedrock_client import (
    AWS_DEFAULT_REGION_VARIABLE,
    AWS_REGION_VARIABLE,
    BedrockClient,
    BedrockClientError,
    BedrockDriver,
    Boto3BedrockClient,
    boto3_driver,
    configure_bedrock,
)
from azathoth.providers.bedrock_configuration import (
    BEDROCK_ENABLED_VARIABLE,
    BEDROCK_PRICING_VARIABLE,
    BEDROCK_PROVIDER,
    MISSING_BEDROCK_EXTRA_MESSAGE,
    MISSING_REGION_MESSAGE,
    BedrockConfiguration,
    BedrockConfigurationError,
    BedrockPricing,
    BedrockUnavailableError,
    bedrock_enabled,
    load_bedrock_pricing,
)
from azathoth.providers.bedrock_directory import BedrockModelDirectory
from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.catalog_loader import ModelCatalogLoader
from azathoth.providers.deterministic import DeterministicLanguageModel
from azathoth.providers.exceptions import (
    ModelDiscoveryError,
    ModelExecutionError,
    UnsupportedModelRequestError,
)
from azathoth.providers.execution import ModelExecutor
from azathoth.providers.memory_portfolio_repository import (
    InMemoryModelPortfolioRepository,
    require_model_portfolio_repository,
)
from azathoth.providers.memory_provider_observation_repository import (
    InMemoryProviderModelObservationRepository,
    require_provider_model_observation_repository,
)
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
from azathoth.providers.openrouter_directory import (
    OpenRouterModelDirectory,
)
from azathoth.providers.openrouter_models import OpenRouterConfiguration
from azathoth.providers.openrouter_registry import (
    OpenRouterModelRegistryLoader,
)
from azathoth.providers.portfolio import (
    ModelPortfolio,
    ModelPortfolioEntry,
)
from azathoth.providers.portfolio_catalog import (
    model_catalog_for_portfolio,
)
from azathoth.providers.portfolio_loader import (
    ModelPortfolioLoader,
)
from azathoth.providers.portfolio_repository import (
    ModelPortfolioRepository,
)
from azathoth.providers.protocol import LanguageModel
from azathoth.providers.provider_catalog_synchronizer import (
    ProviderModelCatalogSynchronizer,
)
from azathoth.providers.provider_directory import (
    ProviderModelDirectory,
)
from azathoth.providers.provider_metadata import (
    model_metadata_from_provider_model,
)
from azathoth.providers.provider_models import (
    ProviderModel,
    ProviderModelObservation,
)
from azathoth.providers.provider_observation_repository import (
    ProviderModelObservationRepository,
)
from azathoth.providers.provider_observer import (
    ProviderModelObservationUpdate,
    ProviderModelObserver,
)
from azathoth.providers.query import ModelQuery
from azathoth.providers.registry import LanguageModelRegistry
from azathoth.providers.repository import ModelRepository
from azathoth.providers.requirements import ModelRequirements
from azathoth.providers.sql_portfolio_repository import (
    MODEL_PORTFOLIO_TABLES,
    SqlModelPortfolioRepository,
)
from azathoth.providers.sql_provider_observation_repository import (
    PROVIDER_MODEL_OBSERVATION_TABLES,
    SqlProviderModelObservationRepository,
)
from azathoth.providers.sql_repository import MODEL_TABLES, SqlModelRepository
from azathoth.providers.sqlite_portfolio_repository import (
    SQLiteModelPortfolioRepository,
)
from azathoth.providers.sqlite_provider_observation_repository import (
    SQLiteProviderModelObservationRepository,
)
from azathoth.providers.sqlite_repository import SQLiteModelRepository

__all__ = [
    "AWS_DEFAULT_REGION_VARIABLE",
    "AWS_REGION_VARIABLE",
    "BLOCKED_STOP_REASONS",
    "BedrockLanguageModel",
    "BedrockModelRegistryLoader",
    "BEDROCK_ENABLED_VARIABLE",
    "BEDROCK_PRICING_VARIABLE",
    "BEDROCK_PROVIDER",
    "MISSING_BEDROCK_EXTRA_MESSAGE",
    "MISSING_REGION_MESSAGE",
    "BedrockClient",
    "BedrockClientError",
    "BedrockConfiguration",
    "BedrockConfigurationError",
    "BedrockDriver",
    "BedrockModelDirectory",
    "BedrockPricing",
    "BedrockUnavailableError",
    "Boto3BedrockClient",
    "bedrock_enabled",
    "boto3_driver",
    "configure_bedrock",
    "load_bedrock_pricing",
    "MODEL_PORTFOLIO_TABLES",
    "MODEL_TABLES",
    "PROVIDER_MODEL_OBSERVATION_TABLES",
    "SqlModelPortfolioRepository",
    "SqlModelRepository",
    "SqlProviderModelObservationRepository",
    "DeterministicLanguageModel",
    "InMemoryModelRepository",
    "InMemoryModelPortfolioRepository",
    "InMemoryProviderModelObservationRepository",
    "LanguageModel",
    "LanguageModelRegistry",
    "ModelCapability",
    "ModelCatalog",
    "ModelCatalogLoader",
    "ModelDiscoveryError",
    "ModelExecutionError",
    "ModelExecutor",
    "ModelMetadata",
    "ModelModality",
    "ModelPortfolio",
    "ModelPortfolioEntry",
    "ModelPortfolioLoader",
    "ModelPortfolioRepository",
    "ModelPricing",
    "ModelQuery",
    "ModelRequest",
    "ModelRepository",
    "ModelRequirements",
    "ModelResponse",
    "OpenRouterConfiguration",
    "OpenRouterLanguageModel",
    "OpenRouterModelDirectory",
    "OpenRouterModelRegistryLoader",
    "Prompt",
    "ProviderModel",
    "ProviderModelCatalogSynchronizer",
    "ProviderModelDirectory",
    "ProviderModelObservation",
    "ProviderModelObservationRepository",
    "ProviderModelObservationUpdate",
    "ProviderModelObserver",
    "SQLiteModelRepository",
    "SQLiteModelPortfolioRepository",
    "SQLiteProviderModelObservationRepository",
    "UnsupportedModelRequestError",
    "model_catalog_for_portfolio",
    "model_metadata_from_provider_model",
    "require_model_portfolio_repository",
    "require_model_repository",
    "require_provider_model_observation_repository",
]
