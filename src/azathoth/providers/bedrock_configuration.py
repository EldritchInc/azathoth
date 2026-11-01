"""Turning Amazon Bedrock on, and pricing its models (ADR 0103)."""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from azathoth.providers.models import ModelPricing

BEDROCK_PROVIDER: Final = "bedrock"
"""The provider of every Bedrock model, as in `bedrock/<model id>`."""

BEDROCK_ENABLED_VARIABLE: Final = "AZATHOTH_BEDROCK"
"""The variable that turns Bedrock on: `1`, `true`, `yes` or `on`."""

BEDROCK_PRICING_VARIABLE: Final = "AZATHOTH_BEDROCK_PRICING"
"""The variable naming the operator's Bedrock pricing document."""

_ENABLED_VALUES: Final = frozenset({"1", "true", "yes", "on"})

MISSING_BEDROCK_EXTRA_MESSAGE: Final = (
    "AZATHOTH_BEDROCK is set, but boto3 is not installed; install azathoth-ai[bedrock]."
)

MISSING_REGION_MESSAGE: Final = (
    "AZATHOTH_BEDROCK is set, but no AWS region is configured; set AWS_REGION."
)


class BedrockUnavailableError(RuntimeError):
    """Raised when Bedrock is turned on without the `bedrock` extra installed."""

    def __init__(
        self,
    ) -> None:
        super().__init__(MISSING_BEDROCK_EXTRA_MESSAGE)


class BedrockConfigurationError(ValueError):
    """Raised when the environment configures Bedrock in a way that cannot be used."""


class BedrockPricing(BaseModel):
    """The operator's prices for Bedrock models, keyed by Bedrock model ID.

    A model the document does not price has unknown pricing. A priced model
    the region does not offer is never looked up, so one document may serve
    several regions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1

    models: Mapping[Annotated[str, Field(min_length=1)], ModelPricing] = Field(
        default_factory=dict,
    )

    def price(
        self,
        model_id: str,
    ) -> ModelPricing | None:
        """Return one model's price, or None when the document does not price it."""

        return self.models.get(model_id)


class BedrockConfiguration(BaseModel):
    """What Azathoth needs to call Bedrock in one region."""

    model_config = ConfigDict(frozen=True)

    region: str = Field(min_length=1)

    timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
    )

    max_attempts: int = Field(
        default=3,
        ge=1,
    )

    pricing: BedrockPricing = Field(default_factory=BedrockPricing)


def bedrock_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether the environment turns Bedrock on."""

    source = os.environ if environ is None else environ

    return source.get(BEDROCK_ENABLED_VARIABLE, "").strip().lower() in _ENABLED_VALUES


def load_bedrock_pricing(
    path: Path,
) -> BedrockPricing:
    """Read one Bedrock pricing document.

    Raises:
        BedrockConfigurationError: The file cannot be read, is not JSON, or
            is not a pricing document.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _invalid_pricing(path, exc.strerror or str(exc)) from exc

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _invalid_pricing(path, f"invalid JSON at line {exc.lineno}") from exc

    try:
        return BedrockPricing.model_validate(document)
    except ValidationError as exc:
        raise _invalid_pricing(path, _first_error(exc)) from exc


def _invalid_pricing(
    path: Path,
    reason: str,
) -> BedrockConfigurationError:
    """Return the error for a pricing document that cannot be used."""

    return BedrockConfigurationError(
        f"{BEDROCK_PRICING_VARIABLE} {path} is not a valid Bedrock pricing document: {reason}."
    )


def _first_error(
    error: ValidationError,
) -> str:
    """Return the first validation error, with where it is in the document."""

    first = error.errors(include_url=False)[0]
    location = ".".join(str(part) for part in first["loc"])
    message = str(first["msg"])

    return f"{location}: {message}" if location else message


__all__ = [
    "BEDROCK_ENABLED_VARIABLE",
    "BEDROCK_PRICING_VARIABLE",
    "BEDROCK_PROVIDER",
    "MISSING_BEDROCK_EXTRA_MESSAGE",
    "MISSING_REGION_MESSAGE",
    "BedrockConfiguration",
    "BedrockConfigurationError",
    "BedrockPricing",
    "BedrockUnavailableError",
    "bedrock_enabled",
    "load_bedrock_pricing",
]
