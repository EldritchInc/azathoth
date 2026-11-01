"""Tests for discovering the models one Bedrock region offers (ADR 0103)."""

import asyncio

import pytest

from azathoth.providers import (
    BedrockClientError,
    BedrockConfiguration,
    BedrockModelDirectory,
    BedrockPricing,
    InMemoryProviderModelObservationRepository,
    ModelCapability,
    ModelDiscoveryError,
    ModelModality,
    ModelPricing,
    ProviderModel,
    ProviderModelCatalogSynchronizer,
    ProviderModelDirectory,
    ProviderModelObserver,
)
from tests.providers.fake_bedrock import FakeBedrockClient, foundation_model, inference_profile

NOVA_PRO = "amazon.nova-pro-v1:0"

NOVA_LITE = "amazon.nova-lite-v1:0"

CLAUDE = "anthropic.claude-sonnet-4-20250514-v1:0"

US_CLAUDE = "us.anthropic.claude-sonnet-4-20250514-v1:0"

TITAN_EMBED = "amazon.titan-embed-text-v2:0"

NOVA_PRO_PRICE = ModelPricing(
    input_usd_per_million_tokens=0.8,
    output_usd_per_million_tokens=3.2,
)

US_CLAUDE_PRICE = ModelPricing(
    input_usd_per_million_tokens=3.0,
    output_usd_per_million_tokens=15.0,
)


def directory(
    client: FakeBedrockClient,
    *,
    pricing: BedrockPricing | None = None,
) -> BedrockModelDirectory:
    """Return a directory over a fake client, in us-east-1."""

    return BedrockModelDirectory(
        BedrockConfiguration(region="us-east-1", pricing=pricing or BedrockPricing()),
        client,
    )


def discovered(
    client: FakeBedrockClient,
    *,
    pricing: BedrockPricing | None = None,
) -> tuple[ProviderModel, ...]:
    """Return every model a directory over a fake client discovers."""

    return asyncio.run(directory(client, pricing=pricing).models())


def identifiers(
    models: tuple[ProviderModel, ...],
) -> list[str]:
    """Return each model's provider-qualified identifier, in order."""

    return [model.identifier for model in models]


# The contract


def test_the_directory_is_a_provider_model_directory() -> None:
    contract: ProviderModelDirectory = directory(FakeBedrockClient())

    assert contract.provider == "bedrock"


def test_a_region_with_no_models_discovers_none() -> None:
    assert discovered(FakeBedrockClient()) == ()


# Foundation models


def test_an_active_on_demand_text_model_is_discovered_by_its_model_id() -> None:
    client = FakeBedrockClient(
        foundation_models=[
            foundation_model(NOVA_PRO, name="Nova Pro", inputs=("TEXT", "IMAGE", "VIDEO")),
        ],
    )

    assert discovered(client) == (
        ProviderModel(
            provider="bedrock",
            model=NOVA_PRO,
            display_name="Nova Pro",
            input_modalities=frozenset(
                {ModelModality.TEXT, ModelModality.IMAGE, ModelModality.VIDEO}
            ),
            output_modalities=frozenset({ModelModality.TEXT}),
            capabilities=frozenset({ModelCapability.STREAMING, ModelCapability.VISION}),
        ),
    )


def test_its_identifier_is_qualified_by_bedrock() -> None:
    client = FakeBedrockClient(foundation_models=[foundation_model(NOVA_PRO)])

    assert identifiers(discovered(client)) == [f"bedrock/{NOVA_PRO}"]


def test_a_model_that_cannot_stream_is_not_marked_streaming() -> None:
    client = FakeBedrockClient(foundation_models=[foundation_model(NOVA_PRO, streaming=False)])

    (model,) = discovered(client)

    assert model.capabilities == frozenset()


def test_context_windows_and_output_limits_are_unknown() -> None:
    client = FakeBedrockClient(foundation_models=[foundation_model(NOVA_PRO)])

    (model,) = discovered(client)

    assert model.context_window_tokens is None
    assert model.maximum_output_tokens is None


@pytest.mark.parametrize(
    "model",
    (
        foundation_model("amazon.titan-embed-text-v2:0", outputs=("EMBEDDING",)),
        foundation_model("amazon.nova-canvas-v1:0", outputs=("IMAGE",)),
        foundation_model("anthropic.claude-v2", status="LEGACY"),
        foundation_model("meta.llama3-70b-instruct-v1:0", inference_types=("PROVISIONED",)),
        foundation_model(CLAUDE, inference_types=("INFERENCE_PROFILE",)),
    ),
    ids=("embedding", "image", "legacy", "provisioned-only", "profile-only"),
)
def test_a_model_that_is_not_an_active_on_demand_text_model_is_left_out(
    model: dict[str, object],
) -> None:
    assert discovered(FakeBedrockClient(foundation_models=[model])) == ()


def test_a_model_without_a_lifecycle_is_left_out() -> None:
    model = foundation_model(NOVA_PRO)
    del model["modelLifecycle"]

    assert discovered(FakeBedrockClient(foundation_models=[model])) == ()


def test_modalities_azathoth_does_not_know_are_left_out() -> None:
    client = FakeBedrockClient(
        foundation_models=[foundation_model(NOVA_PRO, inputs=("TEXT", "SPEECH", "HOLOGRAM"))],
    )

    (model,) = discovered(client)

    assert model.input_modalities == frozenset({ModelModality.TEXT, ModelModality.AUDIO})


# Inference profiles


def test_a_system_defined_profile_is_discovered_by_its_profile_id() -> None:
    client = FakeBedrockClient(
        foundation_models=[
            foundation_model(
                CLAUDE,
                inputs=("TEXT", "IMAGE"),
                inference_types=("INFERENCE_PROFILE",),
            ),
        ],
        inference_profile_pages=[[inference_profile(US_CLAUDE, CLAUDE, name="US Claude Sonnet 4")]],
    )

    (model,) = discovered(client)

    assert model == ProviderModel(
        provider="bedrock",
        model=US_CLAUDE,
        display_name="US Claude Sonnet 4",
        input_modalities=frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
        output_modalities=frozenset({ModelModality.TEXT}),
        capabilities=frozenset({ModelCapability.STREAMING, ModelCapability.VISION}),
    )


def test_a_model_and_a_profile_for_it_are_both_discovered_model_first() -> None:
    client = FakeBedrockClient(
        foundation_models=[foundation_model(NOVA_PRO)],
        inference_profile_pages=[[inference_profile("us.amazon.nova-pro-v1:0", NOVA_PRO)]],
    )

    assert identifiers(discovered(client)) == [
        f"bedrock/{NOVA_PRO}",
        "bedrock/us.amazon.nova-pro-v1:0",
    ]


def test_every_page_of_profiles_is_followed() -> None:
    client = FakeBedrockClient(
        foundation_models=[foundation_model(CLAUDE, inference_types=("INFERENCE_PROFILE",))],
        inference_profile_pages=[
            [inference_profile(US_CLAUDE, CLAUDE)],
            [inference_profile("eu.anthropic.claude-sonnet-4-20250514-v1:0", CLAUDE)],
            [inference_profile("global.anthropic.claude-sonnet-4-20250514-v1:0", CLAUDE)],
        ],
    )

    assert identifiers(discovered(client)) == [
        f"bedrock/{US_CLAUDE}",
        "bedrock/eu.anthropic.claude-sonnet-4-20250514-v1:0",
        "bedrock/global.anthropic.claude-sonnet-4-20250514-v1:0",
    ]
    assert [call for call in client.calls if call[0] == "list_inference_profiles"] == [
        ("list_inference_profiles", ""),
        ("list_inference_profiles", "page-1"),
        ("list_inference_profiles", "page-2"),
    ]


def test_a_page_token_that_repeats_ends_the_listing() -> None:
    class Repeating(FakeBedrockClient):
        def list_inference_profiles(
            self,
            next_token: str | None = None,
        ) -> dict[str, object]:
            self.calls.append(("list_inference_profiles", next_token or ""))

            return {"inferenceProfileSummaries": [], "nextToken": "again"}

    client = Repeating()

    assert discovered(client) == ()
    assert len([call for call in client.calls if call[0] == "list_inference_profiles"]) == 2


@pytest.mark.parametrize(
    "profile",
    (
        inference_profile(US_CLAUDE, CLAUDE, status="INACTIVE"),
        inference_profile(US_CLAUDE, CLAUDE, profile_type="APPLICATION"),
        inference_profile(US_CLAUDE, "anthropic.claude-unknown-v1:0"),
        inference_profile(US_CLAUDE),
    ),
    ids=("inactive", "application", "routes-to-an-unlisted-model", "routes-to-nothing"),
)
def test_a_profile_that_is_not_active_system_defined_and_routed_is_left_out(
    profile: dict[str, object],
) -> None:
    client = FakeBedrockClient(
        foundation_models=[foundation_model(CLAUDE, inference_types=("INFERENCE_PROFILE",))],
        inference_profile_pages=[[profile]],
    )

    assert discovered(client) == ()


def test_a_profile_routed_to_a_legacy_or_non_text_model_is_left_out() -> None:
    client = FakeBedrockClient(
        foundation_models=[
            foundation_model(CLAUDE, status="LEGACY"),
            foundation_model(TITAN_EMBED, outputs=("EMBEDDING",)),
        ],
        inference_profile_pages=[
            [
                inference_profile(US_CLAUDE, CLAUDE),
                inference_profile(f"us.{TITAN_EMBED}", TITAN_EMBED),
            ]
        ],
    )

    assert discovered(client) == ()


def test_a_profile_listed_twice_is_discovered_once() -> None:
    client = FakeBedrockClient(
        foundation_models=[foundation_model(CLAUDE, inference_types=("INFERENCE_PROFILE",))],
        inference_profile_pages=[
            [inference_profile(US_CLAUDE, CLAUDE)],
            [inference_profile(US_CLAUDE, CLAUDE, name="Again")],
        ],
    )

    (model,) = discovered(client)

    assert model.display_name == US_CLAUDE


# Pricing


def test_models_are_priced_from_the_document_by_their_bedrock_id() -> None:
    client = FakeBedrockClient(
        foundation_models=[
            foundation_model(NOVA_PRO),
            foundation_model(NOVA_LITE),
            foundation_model(CLAUDE, inference_types=("INFERENCE_PROFILE",)),
        ],
        inference_profile_pages=[[inference_profile(US_CLAUDE, CLAUDE)]],
    )
    pricing = BedrockPricing(models={NOVA_PRO: NOVA_PRO_PRICE, US_CLAUDE: US_CLAUDE_PRICE})

    assert {model.model: model.pricing for model in discovered(client, pricing=pricing)} == {
        NOVA_PRO: NOVA_PRO_PRICE,
        NOVA_LITE: None,
        US_CLAUDE: US_CLAUDE_PRICE,
    }


def test_a_priced_model_the_region_does_not_offer_is_ignored() -> None:
    client = FakeBedrockClient(foundation_models=[foundation_model(NOVA_LITE)])
    pricing = BedrockPricing(models={NOVA_PRO: NOVA_PRO_PRICE})

    assert identifiers(discovered(client, pricing=pricing)) == [f"bedrock/{NOVA_LITE}"]


# One model


def test_one_model_is_found_by_its_bedrock_id() -> None:
    client = FakeBedrockClient(
        foundation_models=[
            foundation_model(NOVA_PRO),
            foundation_model(CLAUDE, inference_types=("INFERENCE_PROFILE",)),
        ],
        inference_profile_pages=[[inference_profile(US_CLAUDE, CLAUDE)]],
    )

    found = asyncio.run(directory(client).model(US_CLAUDE))

    assert found is not None
    assert found.identifier == f"bedrock/{US_CLAUDE}"


def test_a_model_the_region_does_not_offer_is_none() -> None:
    client = FakeBedrockClient(foundation_models=[foundation_model(NOVA_PRO)])

    assert asyncio.run(directory(client).model(NOVA_LITE)) is None


def test_an_empty_model_id_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(directory(FakeBedrockClient()).model(""))


# Failures


def test_a_failed_listing_is_a_discovery_error_naming_awss_code() -> None:
    client = FakeBedrockClient(
        listing_error=BedrockClientError("AccessDeniedException", "Not authorized."),
    )

    with pytest.raises(ModelDiscoveryError) as raised:
        discovered(client)

    assert str(raised.value) == (
        "Bedrock model discovery request failed: AccessDeniedException: Not authorized."
    )


def test_a_reply_that_is_not_a_model_listing_is_a_discovery_error() -> None:
    model = foundation_model(NOVA_PRO)
    del model["modelId"]

    with pytest.raises(ModelDiscoveryError) as raised:
        discovered(FakeBedrockClient(foundation_models=[model]))

    assert str(raised.value) == "Bedrock returned invalid model directory data."


def test_a_profile_page_that_is_not_a_listing_is_a_discovery_error() -> None:
    client = FakeBedrockClient(
        inference_profile_pages=[[{"inferenceProfileId": US_CLAUDE}]],
    )

    with pytest.raises(ModelDiscoveryError, match="invalid model directory data"):
        discovered(client)


# Observed into a catalog


def test_discovered_models_are_observed_into_the_current_catalog_with_their_prices() -> None:
    client = FakeBedrockClient(
        foundation_models=[foundation_model(NOVA_PRO), foundation_model(NOVA_LITE)],
    )
    repository = InMemoryProviderModelObservationRepository()
    observer = ProviderModelObserver(
        directory=directory(client, pricing=BedrockPricing(models={NOVA_PRO: NOVA_PRO_PRICE})),
        repository=repository,
    )

    catalog = asyncio.run(ProviderModelCatalogSynchronizer(observers=(observer,)).synchronize())

    assert catalog.identifiers == (f"bedrock/{NOVA_PRO}", f"bedrock/{NOVA_LITE}")
    assert [model.identifier for model in catalog.models_for_provider("bedrock")] == [
        f"bedrock/{NOVA_PRO}",
        f"bedrock/{NOVA_LITE}",
    ]

    nova_pro = catalog.get(f"bedrock/{NOVA_PRO}")
    nova_lite = catalog.get(f"bedrock/{NOVA_LITE}")

    assert nova_pro is not None
    assert nova_pro.pricing == NOVA_PRO_PRICE
    assert nova_lite is not None
    assert nova_lite.pricing is None
    assert len(repository.observations()) == 2
