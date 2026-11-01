"""Opt-in live tests against Amazon Bedrock (ADR 0103).

They call AWS, so they run only with `AZATHOTH_RUN_LIVE_BEDROCK_TESTS=1`,
AWS credentials allowed to list and call Bedrock models, a region, and
`BEDROCK_TEST_MODEL`, a model ID or inference profile ID the region offers.
They may incur AWS charges.
"""

import asyncio
import os

import pytest

from azathoth.providers import (
    BEDROCK_ENABLED_VARIABLE,
    BedrockConfiguration,
    BedrockLanguageModel,
    BedrockModelDirectory,
    Boto3BedrockClient,
    ModelExecutor,
    ModelRequest,
    Prompt,
    configure_bedrock,
)

_LIVE_TEST_FLAG = "AZATHOTH_RUN_LIVE_BEDROCK_TESTS"

_MODEL_VARIABLE = "BEDROCK_TEST_MODEL"

pytestmark = pytest.mark.skipif(
    os.environ.get(_LIVE_TEST_FLAG) != "1",
    reason="Live Bedrock tests require AZATHOTH_RUN_LIVE_BEDROCK_TESTS=1.",
)


@pytest.fixture(scope="module")
def configuration() -> BedrockConfiguration:
    """Return the Bedrock configuration of this environment, turned on."""

    pytest.importorskip("boto3")

    configured = configure_bedrock({**os.environ, BEDROCK_ENABLED_VARIABLE: "1"})

    assert configured is not None

    return configured


@pytest.fixture(scope="module")
def client(
    configuration: BedrockConfiguration,
) -> Boto3BedrockClient:
    """Return a client over boto3, with this environment's credentials."""

    return Boto3BedrockClient(configuration)


@pytest.fixture(scope="module")
def model_id() -> str:
    """Return the Bedrock model the live tests call."""

    value = os.environ.get(_MODEL_VARIABLE, "").strip()

    if not value:
        pytest.skip(f"{_MODEL_VARIABLE} is required for live Bedrock testing.")

    return value


def test_the_region_offers_the_test_model(
    configuration: BedrockConfiguration,
    client: Boto3BedrockClient,
    model_id: str,
) -> None:
    models = asyncio.run(BedrockModelDirectory(configuration, client).models())

    assert models
    assert all(model.provider == "bedrock" for model in models)
    assert model_id in {model.model for model in models}


def test_the_test_model_completes_a_prompt(
    configuration: BedrockConfiguration,
    client: Boto3BedrockClient,
    model_id: str,
) -> None:
    model = BedrockLanguageModel(
        client,
        model_id,
        pricing=configuration.pricing.price(model_id),
    )

    response = asyncio.run(
        ModelExecutor().execute(
            ModelRequest(prompt=Prompt(text="Return exactly the word success.")),
            model,
        )
    )

    assert response.text.strip()
    assert response.provider == "bedrock"
    assert response.model == model_id
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.total_tokens == response.prompt_tokens + response.completion_tokens
    assert response.latency_ms >= 0

    if configuration.pricing.price(model_id) is None:
        assert response.estimated_cost_usd is None
    else:
        assert response.estimated_cost_usd is not None
        assert response.estimated_cost_usd > 0.0
