"""Tests for OpenRouter configuration models."""

import pytest
from pydantic import SecretStr, ValidationError

from azathoth.providers import OpenRouterConfiguration


def create_api_key() -> SecretStr:
    """Create a deterministic OpenRouter API key."""

    return SecretStr("test-openrouter-key")


def create_configuration() -> OpenRouterConfiguration:
    """Create deterministic OpenRouter configuration."""

    return OpenRouterConfiguration(
        api_key=create_api_key(),
    )


def test_openrouter_configuration_records_api_key() -> None:
    configuration = create_configuration()

    assert configuration.api_key.get_secret_value() == "test-openrouter-key"


def test_openrouter_configuration_defaults_base_url() -> None:
    configuration = create_configuration()

    assert configuration.base_url == "https://openrouter.ai/api/v1"


def test_openrouter_configuration_defaults_timeout() -> None:
    configuration = create_configuration()

    assert configuration.timeout_seconds == 30.0


def test_openrouter_configuration_records_custom_base_url() -> None:
    configuration = OpenRouterConfiguration(
        api_key=create_api_key(),
        base_url="https://example.test/api/v1",
    )

    assert configuration.base_url == "https://example.test/api/v1"


def test_openrouter_configuration_records_custom_timeout() -> None:
    configuration = OpenRouterConfiguration(
        api_key=create_api_key(),
        timeout_seconds=10.0,
    )

    assert configuration.timeout_seconds == 10.0


def test_openrouter_configuration_rejects_empty_base_url() -> None:
    with pytest.raises(ValidationError):
        OpenRouterConfiguration(
            api_key=create_api_key(),
            base_url="",
        )


def test_openrouter_configuration_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValidationError):
        OpenRouterConfiguration(
            api_key=create_api_key(),
            timeout_seconds=0.0,
        )


def test_openrouter_configuration_is_immutable() -> None:
    configuration = create_configuration()

    with pytest.raises(ValidationError):
        configuration.timeout_seconds = 10.0


def test_openrouter_configuration_masks_api_key() -> None:
    configuration = create_configuration()

    assert "test-openrouter-key" not in repr(configuration)
    assert "test-openrouter-key" not in str(configuration)


def test_openrouter_configuration_masks_api_key_in_json() -> None:
    configuration = create_configuration()

    serialized = configuration.model_dump_json()

    assert "test-openrouter-key" not in serialized
    assert "**********" in serialized
