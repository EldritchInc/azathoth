"""Tests for Azathoth CLI runtime configuration."""

from pathlib import Path

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    DEFAULT_DATABASE,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
    CliRuntimeConfiguration,
)


def test_cli_runtime_configuration_uses_default_database() -> None:
    configuration = CliRuntimeConfiguration.from_environment({})

    assert configuration.database == DEFAULT_DATABASE


def test_cli_runtime_configuration_reads_database_from_environment() -> None:
    configuration = CliRuntimeConfiguration.from_environment(
        {
            DATABASE_ENVIRONMENT_VARIABLE: ("/tmp/example-azathoth.db"),
        }
    )

    assert configuration.database == Path("/tmp/example-azathoth.db")


def test_cli_runtime_configuration_has_no_provider_credentials_by_default() -> None:
    configuration = CliRuntimeConfiguration.from_environment({})

    assert configuration.openrouter_api_key is None


def test_cli_runtime_configuration_reads_openrouter_api_key() -> None:
    configuration = CliRuntimeConfiguration.from_environment(
        {
            OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE: ("test-secret-key"),
        }
    )

    assert configuration.openrouter_api_key is not None

    assert configuration.openrouter_api_key.get_secret_value() == "test-secret-key"


def test_cli_runtime_configuration_does_not_expose_openrouter_secret() -> None:
    configuration = CliRuntimeConfiguration.from_environment(
        {
            OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE: ("test-secret-key"),
        }
    )

    representation = repr(configuration)

    assert "test-secret-key" not in representation


def test_cli_runtime_configuration_ignores_empty_database_environment_value() -> None:
    configuration = CliRuntimeConfiguration.from_environment(
        {
            DATABASE_ENVIRONMENT_VARIABLE: "",
        }
    )

    assert configuration.database == DEFAULT_DATABASE


def test_cli_runtime_configuration_ignores_empty_openrouter_api_key() -> None:
    configuration = CliRuntimeConfiguration.from_environment(
        {
            OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE: "",
        }
    )

    assert configuration.openrouter_api_key is None
