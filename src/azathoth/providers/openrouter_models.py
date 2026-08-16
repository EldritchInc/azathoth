"""Configuration models for the OpenRouter provider."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class OpenRouterConfiguration(BaseModel):
    """Configuration required to access the OpenRouter API."""

    model_config = ConfigDict(frozen=True)

    api_key: SecretStr
    base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        min_length=1,
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
    )
