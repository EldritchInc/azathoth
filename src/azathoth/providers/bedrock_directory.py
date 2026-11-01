"""Discover the models one Bedrock region offers (ADR 0103)."""

import asyncio
from collections.abc import Callable, Mapping
from functools import partial
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from azathoth.providers.bedrock_client import BedrockClient, BedrockClientError
from azathoth.providers.bedrock_configuration import BEDROCK_PROVIDER, BedrockConfiguration
from azathoth.providers.exceptions import ModelDiscoveryError
from azathoth.providers.models import ModelCapability, ModelModality
from azathoth.providers.provider_models import ProviderModel

ACTIVE = "ACTIVE"
"""The lifecycle and profile status of a model Azathoth lists."""

ON_DEMAND = "ON_DEMAND"
"""The inference type of a foundation model that may be called by its own ID."""

TEXT = "TEXT"
"""Bedrock's name for text, which every model Azathoth lists must output."""

FOUNDATION_MODEL_ARN_MARKER = ":foundation-model/"
"""What precedes the model ID in the ARN of a foundation model."""

_Shape = TypeVar("_Shape", bound=BaseModel)

_MODALITIES: Mapping[str, ModelModality] = {
    "TEXT": ModelModality.TEXT,
    "IMAGE": ModelModality.IMAGE,
    "EMBEDDING": ModelModality.EMBEDDINGS,
    "SPEECH": ModelModality.AUDIO,
    "AUDIO": ModelModality.AUDIO,
    "VIDEO": ModelModality.VIDEO,
}
"""Bedrock's modalities, as Azathoth's. Any other is left out."""


class _Lifecycle(BaseModel):
    """A foundation model's lifecycle."""

    model_config = ConfigDict(frozen=True)

    status: str


class _FoundationModel(BaseModel):
    """The part of a foundation model summary Azathoth reads."""

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(alias="modelId", min_length=1)
    model_name: str = Field(alias="modelName", min_length=1)
    input_modalities: tuple[str, ...] = Field(alias="inputModalities", default=())
    output_modalities: tuple[str, ...] = Field(alias="outputModalities", default=())
    inference_types: tuple[str, ...] = Field(alias="inferenceTypesSupported", default=())
    streaming: bool = Field(alias="responseStreamingSupported", default=False)
    lifecycle: _Lifecycle | None = Field(alias="modelLifecycle", default=None)

    @property
    def active(
        self,
    ) -> bool:
        return self.lifecycle is not None and self.lifecycle.status == ACTIVE

    @property
    def outputs_text(
        self,
    ) -> bool:
        return TEXT in self.output_modalities


class _FoundationModels(BaseModel):
    """A reply of `ListFoundationModels`."""

    model_config = ConfigDict(frozen=True)

    models: tuple[_FoundationModel, ...] = Field(alias="modelSummaries", default=())


class _ProfileModel(BaseModel):
    """One model an inference profile routes to."""

    model_config = ConfigDict(frozen=True)

    arn: str = Field(alias="modelArn", default="")

    @property
    def model_id(
        self,
    ) -> str | None:
        """Return the foundation model's ID, from its ARN."""

        _, marker, model_id = self.arn.partition(FOUNDATION_MODEL_ARN_MARKER)

        return model_id if marker and model_id else None


class _InferenceProfile(BaseModel):
    """The part of an inference profile summary Azathoth reads."""

    model_config = ConfigDict(frozen=True)

    profile_id: str = Field(alias="inferenceProfileId", min_length=1)
    profile_name: str = Field(alias="inferenceProfileName", min_length=1)
    status: str
    type: str
    models: tuple[_ProfileModel, ...] = ()


class _InferenceProfiles(BaseModel):
    """One page of a reply of `ListInferenceProfiles`."""

    model_config = ConfigDict(frozen=True)

    profiles: tuple[_InferenceProfile, ...] = Field(
        alias="inferenceProfileSummaries",
        default=(),
    )
    next_token: str | None = Field(alias="nextToken", default=None)


class BedrockModelDirectory:
    """Discover the text models one Bedrock region offers.

    It lists every active foundation model that outputs text and can be
    called on demand, by its model ID, and every active system-defined
    inference profile that routes to such a model, by its profile ID. Each is
    priced from the operator's pricing document, or left unpriced.
    """

    def __init__(
        self,
        configuration: BedrockConfiguration,
        client: BedrockClient,
    ) -> None:
        self._configuration = configuration
        self._client = client

    @property
    def provider(
        self,
    ) -> str:
        """Return the Bedrock provider identifier."""

        return BEDROCK_PROVIDER

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Return every text model the region currently offers.

        Raises:
            ModelDiscoveryError: Bedrock could not be asked, or replied with
                something that is not a model listing.
        """

        return await asyncio.to_thread(self._discover)

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one model the region currently offers, by its Bedrock ID."""

        if not identifier:
            raise ValueError("Bedrock model identifier must not be empty.")

        for model in await self.models():
            if model.model == identifier:
                return model

        return None

    def _discover(
        self,
    ) -> tuple[ProviderModel, ...]:
        """List the region's foundation models and inference profiles."""

        foundation_models = self._foundation_models()
        by_id = {model.model_id: model for model in foundation_models}

        discovered: dict[str, ProviderModel] = {}

        for model in foundation_models:
            if model.active and model.outputs_text and ON_DEMAND in model.inference_types:
                discovered.setdefault(
                    model.model_id,
                    self._provider_model(model.model_id, model.model_name, model),
                )

        for profile in self._inference_profiles():
            routed = _routed_model(profile, by_id)

            if profile.status == ACTIVE and routed is not None:
                discovered.setdefault(
                    profile.profile_id,
                    self._provider_model(profile.profile_id, profile.profile_name, routed),
                )

        return tuple(discovered.values())

    def _foundation_models(
        self,
    ) -> tuple[_FoundationModel, ...]:
        """Return the region's foundation models."""

        reply = _ask(self._client.list_foundation_models)

        return _parse(_FoundationModels, reply).models

    def _inference_profiles(
        self,
    ) -> tuple[_InferenceProfile, ...]:
        """Return every page of the region's system-defined inference profiles."""

        profiles: list[_InferenceProfile] = []
        next_token: str | None = None
        seen: set[str] = set()

        while True:
            reply = _ask(partial(self._client.list_inference_profiles, next_token))
            page = _parse(_InferenceProfiles, reply)

            profiles.extend(page.profiles)

            if not page.next_token or page.next_token in seen:
                return tuple(profiles)

            seen.add(page.next_token)
            next_token = page.next_token

    def _provider_model(
        self,
        model_id: str,
        display_name: str,
        model: _FoundationModel,
    ) -> ProviderModel:
        """Return one listed model, with the modalities of the model it runs on."""

        input_modalities = _modalities(model.input_modalities)

        capabilities: set[ModelCapability] = set()

        if model.streaming:
            capabilities.add(ModelCapability.STREAMING)

        if ModelModality.IMAGE in input_modalities:
            capabilities.add(ModelCapability.VISION)

        return ProviderModel(
            provider=BEDROCK_PROVIDER,
            model=model_id,
            display_name=display_name,
            input_modalities=input_modalities,
            output_modalities=_modalities(model.output_modalities),
            capabilities=frozenset(capabilities),
            pricing=self._configuration.pricing.price(model_id),
        )


def _routed_model(
    profile: _InferenceProfile,
    foundation_models: Mapping[str, _FoundationModel],
) -> _FoundationModel | None:
    """Return the active text model a system-defined profile routes to, if any."""

    if profile.type != "SYSTEM_DEFINED":
        return None

    for routed in profile.models:
        model = foundation_models.get(routed.model_id or "")

        if model is not None and model.active and model.outputs_text:
            return model

    return None


def _modalities(
    modalities: tuple[str, ...],
) -> frozenset[ModelModality]:
    """Return Bedrock's modalities that Azathoth recognizes."""

    return frozenset(
        _MODALITIES[modality.upper()] for modality in modalities if modality.upper() in _MODALITIES
    )


def _ask(
    call: Callable[[], Mapping[str, object]],
) -> Mapping[str, object]:
    """Make one listing call, as a discovery failure if it fails."""

    try:
        return call()
    except BedrockClientError as exc:
        detail = str(exc).rstrip(".")

        raise ModelDiscoveryError(f"Bedrock model discovery request failed: {detail}.") from exc


def _parse(
    shape: type[_Shape],
    reply: Mapping[str, object],
) -> _Shape:
    """Read one listing reply, as a discovery failure if it is not one."""

    try:
        return shape.model_validate(reply)
    except ValidationError as exc:
        raise ModelDiscoveryError("Bedrock returned invalid model directory data.") from exc


__all__ = [
    "BedrockModelDirectory",
]
