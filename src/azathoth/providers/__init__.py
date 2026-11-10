"""Language model provider abstractions."""

from azathoth.providers.bedrock import (
    BEDROCK_IMAGE_FORMATS,
    BEDROCK_MAX_DOCUMENT_BYTES,
    BEDROCK_MAX_DOCUMENTS,
    BEDROCK_MAX_IMAGE_BYTES,
    BEDROCK_MAX_IMAGES,
    BLOCKED_STOP_REASONS,
    BedrockLanguageModel,
    BedrockModelRegistryLoader,
    bedrock_content,
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
from azathoth.providers.content import (
    CONTENT_MODALITIES,
    giving_prompt_content,
    prompt_content_bytes,
)
from azathoth.providers.deterministic import DeterministicLanguageModel
from azathoth.providers.exceptions import (
    ModelDiscoveryError,
    ModelExecutionError,
    PromptContentError,
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
    ContentPart,
    ModelCapability,
    ModelMetadata,
    ModelModality,
    ModelPricing,
    ModelRequest,
    ModelResponse,
    NativeCitation,
    Prompt,
    PromptPart,
    TextPart,
)
from azathoth.providers.openrouter import (
    OPENROUTER_PDF_ENGINE,
    OpenRouterLanguageModel,
    openrouter_request,
)
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
    MODEL_PORTFOLIO_PROVENANCE_TABLES,
    MODEL_PORTFOLIO_TABLES,
    PortfolioProvenance,
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
    "BEDROCK_IMAGE_FORMATS",
    "BEDROCK_MAX_DOCUMENTS",
    "BEDROCK_MAX_DOCUMENT_BYTES",
    "BEDROCK_MAX_IMAGES",
    "BEDROCK_MAX_IMAGE_BYTES",
    "CONTENT_MODALITIES",
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
    "bedrock_content",
    "bedrock_enabled",
    "boto3_driver",
    "configure_bedrock",
    "load_bedrock_pricing",
    "MODEL_PORTFOLIO_PROVENANCE_TABLES",
    "MODEL_PORTFOLIO_TABLES",
    "MODEL_TABLES",
    "OPENROUTER_PDF_ENGINE",
    "PROVIDER_MODEL_OBSERVATION_TABLES",
    "PortfolioProvenance",
    "SqlModelPortfolioRepository",
    "SqlModelRepository",
    "SqlProviderModelObservationRepository",
    "ContentPart",
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
    "NativeCitation",
    "Prompt",
    "PromptContentError",
    "PromptPart",
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
    "TextPart",
    "UnsupportedModelRequestError",
    "giving_prompt_content",
    "model_catalog_for_portfolio",
    "model_metadata_from_provider_model",
    "openrouter_request",
    "prompt_content_bytes",
    "require_model_portfolio_repository",
    "require_model_repository",
    "require_provider_model_observation_repository",
]
