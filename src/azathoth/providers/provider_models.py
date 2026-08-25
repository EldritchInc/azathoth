"""Provider-sourced model state and immutable observations."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from azathoth.providers.models import (
    ModelCapability,
    ModelModality,
    ModelPricing,
)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


class ProviderModel(BaseModel):
    """Describe current provider-reported facts about one model."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)

    model: str = Field(min_length=1)

    display_name: str = Field(min_length=1)

    input_modalities: frozenset[ModelModality] = frozenset(
        {
            ModelModality.TEXT,
        }
    )

    output_modalities: frozenset[ModelModality] = frozenset(
        {
            ModelModality.TEXT,
        }
    )

    capabilities: frozenset[ModelCapability] = frozenset()

    context_window_tokens: int | None = Field(
        default=None,
        gt=0,
    )

    maximum_output_tokens: int | None = Field(
        default=None,
        gt=0,
    )

    pricing: ModelPricing | None = None

    @property
    def identifier(self) -> str:
        """Return the provider-qualified model identifier."""

        return f"{self.provider}/{self.model}"

    @property
    def fingerprint(self) -> str:
        """Return a stable fingerprint of provider-reported facts."""

        payload = self.model_dump_json(
            exclude_none=False,
        )

        return sha256(payload.encode("utf-8")).hexdigest()


class ProviderModelObservation(BaseModel):
    """Record provider model facts observed by Azathoth at one moment."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    observed_at: datetime = Field(default_factory=utc_now)

    model: ProviderModel

    @property
    def provider(self) -> str:
        """Return the observed provider."""

        return self.model.provider

    @property
    def model_identifier(self) -> str:
        """Return the provider-native model identifier."""

        return self.model.model

    @property
    def identifier(self) -> str:
        """Return the provider-qualified model identifier."""

        return self.model.identifier

    @property
    def fingerprint(self) -> str:
        """Return the fingerprint of the observed provider facts."""

        return self.model.fingerprint
