"""Discover normalized language model state from OpenRouter."""

from decimal import Decimal, InvalidOperation

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

from azathoth.providers.exceptions import (
    ModelDiscoveryError,
)
from azathoth.providers.models import (
    ModelCapability,
    ModelModality,
    ModelPricing,
)
from azathoth.providers.openrouter_models import (
    OpenRouterConfiguration,
)
from azathoth.providers.provider_models import (
    ProviderModel,
)

OPENROUTER_PROVIDER = "openrouter"


class _OpenRouterArchitecture(BaseModel):
    """OpenRouter model architecture metadata used by Azathoth."""

    model_config = ConfigDict(frozen=True)

    input_modalities: tuple[
        str,
        ...,
    ] = ()

    output_modalities: tuple[
        str,
        ...,
    ] = ()


class _OpenRouterPricing(BaseModel):
    """OpenRouter per-unit model pricing used by Azathoth."""

    model_config = ConfigDict(frozen=True)

    prompt: str | None = None
    completion: str | None = None


class _OpenRouterTopProvider(BaseModel):
    """OpenRouter primary-provider model limits used by Azathoth."""

    model_config = ConfigDict(frozen=True)

    max_completion_tokens: int | None = Field(
        default=None,
        gt=0,
    )


class _OpenRouterModel(BaseModel):
    """Subset of OpenRouter model metadata normalized by Azathoth."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)

    name: str = Field(min_length=1)

    context_length: int = Field(gt=0)

    architecture: _OpenRouterArchitecture

    pricing: _OpenRouterPricing | None = None

    supported_parameters: tuple[
        str,
        ...,
    ] = ()

    top_provider: _OpenRouterTopProvider | None = None


class _OpenRouterModelListResponse(BaseModel):
    """OpenRouter response containing discoverable model metadata."""

    model_config = ConfigDict(frozen=True)

    data: tuple[
        _OpenRouterModel,
        ...,
    ]


class _OpenRouterModelResponse(BaseModel):
    """OpenRouter response containing one model."""

    model_config = ConfigDict(frozen=True)

    data: _OpenRouterModel


class OpenRouterModelDirectory:
    """Discover current language model state from OpenRouter."""

    def __init__(
        self,
        configuration: OpenRouterConfiguration,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._configuration = configuration
        self._transport = transport

    @property
    def provider(
        self,
    ) -> str:
        """Return the OpenRouter provider identifier."""

        return OPENROUTER_PROVIDER

    async def models(
        self,
    ) -> tuple[
        ProviderModel,
        ...,
    ]:
        """Return all models currently exposed by OpenRouter."""

        response = await self._get(
            "models",
            params={
                "output_modalities": "all",
            },
        )

        assert response is not None

        try:
            payload = _OpenRouterModelListResponse.model_validate(response.json())
        except (
            ValueError,
            ValidationError,
        ) as exc:
            raise ModelDiscoveryError("OpenRouter returned invalid model directory data.") from exc

        return tuple(_normalize_model(model) for model in payload.data)

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one currently exposed OpenRouter model."""

        if not identifier:
            raise ValueError("OpenRouter model identifier must not be empty.")

        response = await self._get(
            f"model/{identifier}",
            allow_not_found=True,
        )

        if response is None:
            return None

        try:
            payload = _OpenRouterModelResponse.model_validate(response.json())
        except (
            ValueError,
            ValidationError,
        ) as exc:
            raise ModelDiscoveryError(
                f"OpenRouter returned invalid model metadata for {identifier!r}."
            ) from exc

        return _normalize_model(payload.data)

    async def _get(
        self,
        path: str,
        *,
        params: dict[
            str,
            str,
        ]
        | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response | None:
        """Send one OpenRouter model discovery request."""

        base_url = f"{self._configuration.base_url.rstrip('/')}/"

        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=(self._configuration.timeout_seconds),
                transport=self._transport,
                headers={
                    "Authorization": (f"Bearer {self._configuration.api_key.get_secret_value()}"),
                },
            ) as client:
                response = await client.get(
                    path,
                    params=params,
                )

            if allow_not_found and response.status_code == 404:
                return None

            response.raise_for_status()

        except httpx.HTTPError as exc:
            raise ModelDiscoveryError("OpenRouter model discovery request failed.") from exc

        return response


def _normalize_model(
    model: _OpenRouterModel,
) -> ProviderModel:
    """Translate OpenRouter metadata into provider-neutral model state."""

    input_modalities = _normalize_modalities(model.architecture.input_modalities)

    output_modalities = _normalize_modalities(model.architecture.output_modalities)

    capabilities = _normalize_capabilities(
        supported_parameters=model.supported_parameters,
        input_modalities=input_modalities,
    )

    maximum_output_tokens = None

    if model.top_provider is not None:
        maximum_output_tokens = model.top_provider.max_completion_tokens

    return ProviderModel(
        provider=OPENROUTER_PROVIDER,
        model=model.id,
        display_name=model.name,
        input_modalities=input_modalities,
        output_modalities=output_modalities,
        capabilities=capabilities,
        context_window_tokens=model.context_length,
        maximum_output_tokens=maximum_output_tokens,
        pricing=_normalize_pricing(model.pricing),
    )


def _normalize_modalities(
    modalities: tuple[
        str,
        ...,
    ],
) -> frozenset[ModelModality]:
    """Translate recognized OpenRouter modalities."""

    recognized: set[ModelModality] = set()

    for modality in modalities:
        try:
            recognized.add(ModelModality(modality))
        except ValueError:
            continue

    return frozenset(recognized)


def _normalize_capabilities(
    *,
    supported_parameters: tuple[
        str,
        ...,
    ],
    input_modalities: frozenset[ModelModality],
) -> frozenset[ModelCapability]:
    """Translate recognized OpenRouter capabilities."""

    capabilities: set[ModelCapability] = set()

    parameters = frozenset(supported_parameters)

    if "tools" in parameters:
        capabilities.add(ModelCapability.TOOL_USE)

    if "structured_outputs" in parameters:
        capabilities.add(ModelCapability.STRUCTURED_OUTPUT)

    if ModelModality.IMAGE in input_modalities:
        capabilities.add(ModelCapability.VISION)

    return frozenset(capabilities)


def _normalize_pricing(
    pricing: _OpenRouterPricing | None,
) -> ModelPricing | None:
    """Translate OpenRouter per-token pricing to per-million pricing."""

    if pricing is None or pricing.prompt is None or pricing.completion is None:
        return None

    try:
        prompt = Decimal(pricing.prompt)

        completion = Decimal(pricing.completion)

    except InvalidOperation:
        return None

    if prompt < 0 or completion < 0:
        return None

    per_million = Decimal(1_000_000)

    return ModelPricing(
        input_usd_per_million_tokens=float(prompt * per_million),
        output_usd_per_million_tokens=float(completion * per_million),
    )
