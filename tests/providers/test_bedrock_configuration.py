"""Tests for turning Bedrock on, its extra, and its pricing document (ADR 0103)."""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.providers import (
    BEDROCK_ENABLED_VARIABLE,
    BEDROCK_PRICING_VARIABLE,
    BEDROCK_PROVIDER,
    MISSING_BEDROCK_EXTRA_MESSAGE,
    BedrockConfiguration,
    BedrockConfigurationError,
    BedrockPricing,
    BedrockUnavailableError,
    ModelPricing,
    bedrock_enabled,
    load_bedrock_pricing,
)

PROJECT_ROOT = Path(__file__).parents[2]

BOTO3 = "boto3>=1.39,<2"

NOVA_PRO = "amazon.nova-pro-v1:0"

PRICING = {
    "version": 1,
    "models": {
        NOVA_PRO: {
            "input_usd_per_million_tokens": 0.8,
            "output_usd_per_million_tokens": 3.2,
        },
    },
}


def project() -> dict[str, object]:
    """Return the project table of pyproject.toml."""

    document = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    table = document["project"]

    assert isinstance(table, dict)

    return table


def write_pricing(
    tmp_path: Path,
    content: object,
) -> Path:
    """Write one pricing document, and return its path."""

    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(content), encoding="utf-8")

    return path


def refusal(
    path: Path,
    reason: str,
) -> str:
    """Return the message for a pricing document that cannot be used."""

    return f"{BEDROCK_PRICING_VARIABLE} {path} is not a valid Bedrock pricing document: {reason}."


# The extra


def test_the_bedrock_extra_installs_boto3_and_nothing_else() -> None:
    extras = project()["optional-dependencies"]

    assert isinstance(extras, dict)
    assert extras["bedrock"] == [BOTO3]


def test_development_installs_boto3_too() -> None:
    extras = project()["optional-dependencies"]

    assert isinstance(extras, dict)
    assert BOTO3 in extras["dev"]


def test_boto3_is_never_a_runtime_dependency() -> None:
    dependencies = project()["dependencies"]

    assert isinstance(dependencies, list)
    assert not any("boto" in requirement for requirement in dependencies)


def test_importing_the_providers_imports_nothing_of_boto3() -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-c",
            "import sys, azathoth.providers, azathoth.cli; "
            "print(any(name.split('.')[0] in {'boto3', 'botocore'} for name in sys.modules))",
        ),
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout == "False\n"


def test_the_missing_extra_says_what_to_install() -> None:
    assert str(BedrockUnavailableError()) == MISSING_BEDROCK_EXTRA_MESSAGE
    assert MISSING_BEDROCK_EXTRA_MESSAGE == (
        "AZATHOTH_BEDROCK is set, but boto3 is not installed; install azathoth-ai[bedrock]."
    )


# Turning it on


@pytest.mark.parametrize("value", ("1", "true", "TRUE", "yes", "on", " On "))
def test_bedrock_is_on_for_the_enabling_values(
    value: str,
) -> None:
    assert bedrock_enabled({BEDROCK_ENABLED_VARIABLE: value})


@pytest.mark.parametrize("value", ("", "0", "false", "no", "off", "bedrock"))
def test_bedrock_is_off_for_anything_else(
    value: str,
) -> None:
    assert not bedrock_enabled({BEDROCK_ENABLED_VARIABLE: value})


def test_bedrock_is_off_without_the_variable() -> None:
    assert not bedrock_enabled({})


def test_bedrock_reads_the_process_environment_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BEDROCK_ENABLED_VARIABLE, "1")

    assert bedrock_enabled()

    monkeypatch.delenv(BEDROCK_ENABLED_VARIABLE)

    assert not bedrock_enabled()


def test_the_provider_is_named_bedrock() -> None:
    assert BEDROCK_PROVIDER == "bedrock"


# Configuration


def test_configuration_defaults_to_openrouters_timeout_three_attempts_and_no_prices() -> None:
    configuration = BedrockConfiguration(region="us-east-1")

    assert configuration.timeout_seconds == 30.0
    assert configuration.max_attempts == 3
    assert configuration.pricing == BedrockPricing()


@pytest.mark.parametrize(
    "fields",
    (
        {"region": ""},
        {"region": "us-east-1", "timeout_seconds": 0},
        {"region": "us-east-1", "max_attempts": 0},
    ),
)
def test_configuration_rejects_unusable_values(
    fields: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        BedrockConfiguration.model_validate(fields)


# Pricing


def test_a_pricing_document_prices_its_models(
    tmp_path: Path,
) -> None:
    pricing = load_bedrock_pricing(write_pricing(tmp_path, PRICING))

    assert pricing.price(NOVA_PRO) == ModelPricing(
        input_usd_per_million_tokens=0.8,
        output_usd_per_million_tokens=3.2,
    )


def test_a_model_the_document_does_not_price_has_no_price(
    tmp_path: Path,
) -> None:
    pricing = load_bedrock_pricing(write_pricing(tmp_path, PRICING))

    assert pricing.price("amazon.nova-lite-v1:0") is None


def test_an_empty_document_prices_nothing(
    tmp_path: Path,
) -> None:
    pricing = load_bedrock_pricing(write_pricing(tmp_path, {"version": 1}))

    assert pricing == BedrockPricing()
    assert pricing.price(NOVA_PRO) is None


def test_a_missing_document_is_refused(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(BedrockConfigurationError) as raised:
        load_bedrock_pricing(path)

    assert str(raised.value) == refusal(path, "No such file or directory")


def test_a_document_that_is_not_json_is_refused(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pricing.json"
    path.write_text('{\n  "version": 1,\n  oops\n}\n', encoding="utf-8")

    with pytest.raises(BedrockConfigurationError) as raised:
        load_bedrock_pricing(path)

    assert str(raised.value) == refusal(path, "invalid JSON at line 3")


@pytest.mark.parametrize(
    ("content", "reason"),
    (
        ({"version": 2}, "version: Input should be 1"),
        ({"version": 1, "prices": {}}, "prices: Extra inputs are not permitted"),
        (
            {"version": 1, "models": {NOVA_PRO: {"input_usd_per_million_tokens": 0.8}}},
            f"models.{NOVA_PRO}.output_usd_per_million_tokens: Field required",
        ),
        (
            {
                "version": 1,
                "models": {
                    NOVA_PRO: {
                        "input_usd_per_million_tokens": -1,
                        "output_usd_per_million_tokens": 3.2,
                    },
                },
            },
            f"models.{NOVA_PRO}.input_usd_per_million_tokens: "
            "Input should be greater than or equal to 0",
        ),
        ([], "Input should be a valid dictionary or instance of BedrockPricing"),
    ),
)
def test_a_document_that_is_not_a_pricing_document_is_refused_with_its_first_error(
    tmp_path: Path,
    content: object,
    reason: str,
) -> None:
    path = write_pricing(tmp_path, content)

    with pytest.raises(BedrockConfigurationError) as raised:
        load_bedrock_pricing(path)

    assert str(raised.value) == refusal(path, reason)


def test_a_model_id_must_not_be_empty(
    tmp_path: Path,
) -> None:
    content = {
        "version": 1,
        "models": {
            "": {
                "input_usd_per_million_tokens": 0.8,
                "output_usd_per_million_tokens": 3.2,
            },
        },
    }

    with pytest.raises(BedrockConfigurationError):
        load_bedrock_pricing(write_pricing(tmp_path, content))
