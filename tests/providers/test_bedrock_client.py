"""Tests for reaching Bedrock: the configuration, the driver and boto3's client (ADR 0103).

The tests of `Boto3BedrockClient` need boto3, so they are skipped where the
`bedrock` extra is not installed. They never reach AWS: botocore's `Stubber`
answers every call. boto3 ships no types, so it is imported by name.
"""

import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from azathoth.providers import (
    BEDROCK_ENABLED_VARIABLE,
    BEDROCK_PRICING_VARIABLE,
    MISSING_BEDROCK_EXTRA_MESSAGE,
    MISSING_REGION_MESSAGE,
    BedrockClient,
    BedrockClientError,
    BedrockConfiguration,
    BedrockConfigurationError,
    BedrockDriver,
    BedrockPricing,
    BedrockUnavailableError,
    Boto3BedrockClient,
    ModelPricing,
    boto3_driver,
    configure_bedrock,
)
from tests.providers.fake_bedrock import FakeBedrockClient

NOVA_PRO = "amazon.nova-pro-v1:0"

ON = {BEDROCK_ENABLED_VARIABLE: "1"}


def driver(
    region: str | None = "us-east-1",
) -> BedrockDriver:
    """Return a driver whose AWS profile names one region, and whose clients are fakes."""

    return BedrockDriver(
        region=lambda: region,
        client=lambda _configuration: FakeBedrockClient(),
    )


# The protocol


def test_the_fake_client_is_a_bedrock_client() -> None:
    client: BedrockClient = FakeBedrockClient()

    assert client.list_foundation_models() == {"modelSummaries": []}


def test_a_client_error_carries_awss_code_and_message() -> None:
    error = BedrockClientError("ThrottlingException", "Too many requests.")

    assert error.code == "ThrottlingException"
    assert error.message == "Too many requests."
    assert str(error) == "ThrottlingException: Too many requests."


def test_a_client_error_without_a_message_is_its_code() -> None:
    assert str(BedrockClientError("NoCredentialsError", "")) == "NoCredentialsError"


# Configuring from the environment


def test_bedrock_off_is_no_configuration_and_imports_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    assert configure_bedrock({}) is None
    assert configure_bedrock({BEDROCK_ENABLED_VARIABLE: "0"}) is None


def test_bedrock_on_without_the_extra_says_what_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(BedrockUnavailableError) as raised:
        configure_bedrock({**ON, "AWS_REGION": "us-east-1"})

    assert str(raised.value) == MISSING_BEDROCK_EXTRA_MESSAGE


def test_the_boto3_driver_without_the_extra_says_what_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(BedrockUnavailableError):
        boto3_driver()


def test_the_region_is_aws_region_first() -> None:
    configuration = configure_bedrock(
        {**ON, "AWS_REGION": "eu-west-1", "AWS_DEFAULT_REGION": "us-west-2"},
        driver=driver("ap-southeast-2"),
    )

    assert configuration == BedrockConfiguration(region="eu-west-1")


def test_the_region_is_aws_default_region_next() -> None:
    configuration = configure_bedrock(
        {**ON, "AWS_REGION": " ", "AWS_DEFAULT_REGION": "us-west-2"},
        driver=driver("ap-southeast-2"),
    )

    assert configuration == BedrockConfiguration(region="us-west-2")


def test_the_region_is_the_profiles_last() -> None:
    configuration = configure_bedrock(ON, driver=driver("ap-southeast-2"))

    assert configuration == BedrockConfiguration(region="ap-southeast-2")


def test_without_a_region_bedrock_is_refused() -> None:
    with pytest.raises(BedrockConfigurationError) as raised:
        configure_bedrock(ON, driver=driver(None))

    assert str(raised.value) == MISSING_REGION_MESSAGE
    assert MISSING_REGION_MESSAGE == (
        "AZATHOTH_BEDROCK is set, but no AWS region is configured; set AWS_REGION."
    )


def test_the_pricing_document_is_read(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "models": {
                    NOVA_PRO: {
                        "input_usd_per_million_tokens": 0.8,
                        "output_usd_per_million_tokens": 3.2,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    configuration = configure_bedrock(
        {**ON, BEDROCK_PRICING_VARIABLE: str(path)},
        driver=driver(),
    )

    assert configuration is not None
    assert configuration.pricing.price(NOVA_PRO) == ModelPricing(
        input_usd_per_million_tokens=0.8,
        output_usd_per_million_tokens=3.2,
    )


def test_a_blank_pricing_variable_prices_nothing() -> None:
    configuration = configure_bedrock(
        {**ON, BEDROCK_PRICING_VARIABLE: "  "},
        driver=driver(),
    )

    assert configuration is not None
    assert configuration.pricing == BedrockPricing()


def test_an_unusable_pricing_document_is_refused(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(BedrockConfigurationError) as raised:
        configure_bedrock({**ON, BEDROCK_PRICING_VARIABLE: str(path)}, driver=driver())

    assert str(raised.value).startswith(f"{BEDROCK_PRICING_VARIABLE} {path} is not a valid")


# boto3's client


@pytest.fixture
def boto3_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Boto3BedrockClient:
    """Return a client over boto3, with credentials that are never used."""

    pytest.importorskip("boto3")

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    return Boto3BedrockClient(
        BedrockConfiguration(region="eu-central-1", timeout_seconds=12.0, max_attempts=4)
    )


@pytest.fixture
def runtime(
    boto3_client: Boto3BedrockClient,
) -> Iterator[Any]:
    """Stub the client's bedrock-runtime calls."""

    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(boto3_client._runtime) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def control(
    boto3_client: Boto3BedrockClient,
) -> Iterator[Any]:
    """Stub the client's bedrock control-plane calls."""

    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(boto3_client._control) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


CONVERSE_REPLY = {
    "output": {"message": {"role": "assistant", "content": [{"text": "four"}]}},
    "stopReason": "end_turn",
    "usage": {"inputTokens": 7, "outputTokens": 1, "totalTokens": 8},
    "metrics": {"latencyMs": 120},
}


def test_the_clients_use_the_region_timeouts_and_standard_retries(
    boto3_client: Boto3BedrockClient,
) -> None:
    for client in (boto3_client._control, boto3_client._runtime):
        config = client.meta.config

        assert client.meta.region_name == "eu-central-1"
        assert config.connect_timeout == 12.0
        assert config.read_timeout == 12.0
        assert config.retries["mode"] == "standard"
        assert config.retries["total_max_attempts"] == 4

    assert boto3_client._control.meta.service_model.service_name == "bedrock"
    assert boto3_client._runtime.meta.service_model.service_name == "bedrock-runtime"


def test_converse_sends_the_text_as_one_user_message(
    boto3_client: Boto3BedrockClient,
    runtime: Any,
) -> None:
    runtime.add_response(
        "converse",
        CONVERSE_REPLY,
        {
            "modelId": NOVA_PRO,
            "messages": [{"role": "user", "content": [{"text": "How many?"}]}],
        },
    )

    reply = boto3_client.converse(NOVA_PRO, "How many?")

    assert reply["stopReason"] == "end_turn"
    assert reply["usage"] == CONVERSE_REPLY["usage"]


def test_foundation_models_are_listed(
    boto3_client: Boto3BedrockClient,
    control: Any,
) -> None:
    control.add_response("list_foundation_models", {"modelSummaries": []}, {})

    assert boto3_client.list_foundation_models()["modelSummaries"] == []


def test_inference_profiles_are_listed_by_page_and_system_defined_only(
    boto3_client: Boto3BedrockClient,
    control: Any,
) -> None:
    control.add_response(
        "list_inference_profiles",
        {"inferenceProfileSummaries": [], "nextToken": "next"},
        {"typeEquals": "SYSTEM_DEFINED"},
    )
    control.add_response(
        "list_inference_profiles",
        {"inferenceProfileSummaries": []},
        {"typeEquals": "SYSTEM_DEFINED", "nextToken": "next"},
    )

    assert boto3_client.list_inference_profiles()["nextToken"] == "next"
    assert "nextToken" not in boto3_client.list_inference_profiles("next")


def test_an_aws_error_becomes_a_client_error_with_its_code(
    boto3_client: Boto3BedrockClient,
    runtime: Any,
) -> None:
    runtime.add_client_error(
        "converse",
        service_error_code="AccessDeniedException",
        service_message="You don't have access to the model.",
        http_status_code=403,
    )

    with pytest.raises(BedrockClientError) as raised:
        boto3_client.converse(NOVA_PRO, "How many?")

    assert raised.value.code == "AccessDeniedException"
    assert raised.value.message == "You don't have access to the model."


def test_a_botocore_error_becomes_a_client_error_named_for_it(
    boto3_client: Boto3BedrockClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_credentials_error = importlib.import_module("botocore.exceptions").NoCredentialsError

    def no_credentials(**_parameters: object) -> object:
        raise no_credentials_error()

    monkeypatch.setattr(boto3_client._runtime, "converse", no_credentials)

    with pytest.raises(BedrockClientError) as raised:
        boto3_client.converse(NOVA_PRO, "How many?")

    assert raised.value.code == "NoCredentialsError"
    assert raised.value.message == "Unable to locate credentials"


def test_the_boto3_driver_finds_the_profiles_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pytest.importorskip("boto3")

    config = tmp_path / "config"
    config.write_text("[default]\nregion = ca-central-1\n", encoding="utf-8")

    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    assert boto3_driver().region() == "ca-central-1"
