"""Contract tests for provider models and the local portfolio (ADR 0120)."""

import shlex
from collections.abc import Iterator
from typing import NoReturn
from uuid import UUID

import pytest
from pydantic import JsonValue, SecretStr

from azathoth import api
from azathoth.cli.configuration import (
    BEDROCK_ENVIRONMENT_VARIABLES,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
)
from azathoth.cli.parsing import build_parser
from azathoth.evaluation import JudgeEntry
from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import (
    BedrockUnavailableError,
    ModelCapability,
    ModelDiscoveryError,
    ModelModality,
    ModelPortfolioEntry,
    ModelPricing,
    Prompt,
    ProviderModel,
)
from azathoth.revisions import AUTHOR_VARIABLE, Author, content_digest
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

ALPHA = ProviderModel(
    provider="provider-a",
    model="example/alpha",
    display_name="Alpha",
    input_modalities=frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
    output_modalities=frozenset({ModelModality.TEXT}),
    capabilities=frozenset({ModelCapability.VISION, ModelCapability.STRUCTURED_OUTPUT}),
    context_window_tokens=128_000,
    maximum_output_tokens=16_384,
    pricing=ModelPricing(
        input_usd_per_million_tokens=1.25,
        output_usd_per_million_tokens=5.0,
    ),
)
"""A model whose provider publishes everything."""

BETA = ProviderModel(
    provider="provider-b",
    model="example/beta",
    display_name="Beta",
)
"""A model whose provider publishes no context window, output limit or prices."""

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")


class StaticDirectory:
    """A provider directory that serves fixed models, or fails as a provider can."""

    def __init__(
        self,
        provider: str,
        models: tuple[ProviderModel, ...],
        *,
        failure: str | None = None,
    ) -> None:
        self._provider = provider
        self._models = models
        self._failure = failure
        self.calls = 0

    @property
    def provider(
        self,
    ) -> str:
        """Return the provider this directory serves."""

        return self._provider

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Return the fixed models, or raise the configured failure."""

        self.calls += 1

        if self._failure is not None:
            raise ModelDiscoveryError(self._failure)

        return self._models

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one fixed model."""

        return next((model for model in self._models if model.model == identifier), None)


@pytest.fixture
def modelled(
    location: str,
) -> Iterator[api.Azathoth]:
    """Return an instance whose providers serve Alpha and Beta, closed afterwards."""

    with api.Azathoth(
        open_repositories(location),
        directories=(
            StaticDirectory("provider-a", (ALPHA,)),
            StaticDirectory("provider-b", (BETA,)),
        ),
    ) as instance:
        yield instance


def pinned_workflow(
    identifier: str,
) -> WorkflowSpecification:
    """Return a one-step workflow pinned to one exact model."""

    provider, model = identifier.split("/", maxsplit=1)

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="summarize",
            description="Summarize documents.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Summarize prompt",
                        description="Summarize prompt description.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(text="Return exactly OK."),
                    model_selection=FixedModelSelection(provider=provider, model=model),
                ),
            ),
        ),
    )


def parses(
    command: str,
) -> bool:
    """Return whether the CLI accepts one command an API value carries."""

    words = shlex.split(command)

    assert words[0] == "azathoth"

    build_parser().parse_args(words[1:])

    return True


#
# Provider models
#


def test_models_are_listed_from_every_provider_in_order(
    modelled: api.Azathoth,
) -> None:
    models = modelled.models.list()

    assert tuple(model.identifier for model in models) == (ALPHA.identifier, BETA.identifier)


def test_a_model_shows_everything_its_provider_publishes(
    modelled: api.Azathoth,
) -> None:
    model = modelled.models.get(ALPHA.identifier)

    assert model == api.ModelSummary(
        identifier="provider-a/example/alpha",
        provider="provider-a",
        model="example/alpha",
        display_name="Alpha",
        input_modalities=("image", "text"),
        output_modalities=("text",),
        capabilities=("structured_output", "vision"),
        context_window_tokens=128_000,
        maximum_output_tokens=16_384,
        input_usd_per_million_tokens=1.25,
        output_usd_per_million_tokens=5.0,
        authorized=False,
        command="azathoth model show provider-a/example/alpha",
    )
    assert parses(model.command)


def test_what_a_provider_does_not_publish_is_unknown(
    modelled: api.Azathoth,
) -> None:
    model = modelled.models.get(BETA.identifier)

    assert model.context_window_tokens is None
    assert model.maximum_output_tokens is None
    assert model.input_usd_per_million_tokens is None
    assert model.output_usd_per_million_tokens is None
    assert model.capabilities == ()


def test_a_model_identifier_is_quoted_in_its_commands(
    location: str,
) -> None:
    spaced = ProviderModel(provider="provider-a", model="example/with space", display_name="S")

    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory("provider-a", (spaced,)),),
    ) as instance:
        model = instance.models.get(spaced.identifier)
        entry = instance.portfolio.add(spaced.identifier)
        removal = instance.portfolio.remove(spaced.identifier)

    assert model.command == "azathoth model show 'provider-a/example/with space'"
    assert entry.command == model.command
    assert removal.command == "azathoth model deauthorize 'provider-a/example/with space'"
    assert all(parses(command) for command in (model.command, removal.command))


def test_a_model_no_provider_serves_is_not_found(
    modelled: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        modelled.models.get("provider-a/example/missing")

    assert str(raised.value) == "Model 'provider-a/example/missing' is not currently available."


def test_an_instance_without_providers_lists_no_models(
    instance: api.Azathoth,
) -> None:
    assert instance.models.list() == ()


def test_discovery_records_each_providers_models(
    modelled: api.Azathoth,
    location: str,
) -> None:
    modelled.models.list()

    observed = open_repositories(location).provider_observations.latest(ALPHA.identifier)

    assert observed is not None
    assert observed.model == ALPHA


def test_a_provider_that_cannot_be_reached_is_reported(
    location: str,
) -> None:
    directory = StaticDirectory("provider-a", (), failure="OpenRouter could not be reached.")

    with (
        api.Azathoth(open_repositories(location), directories=(directory,)) as instance,
        pytest.raises(api.ProviderUnavailableError) as raised,
    ):
        instance.models.list()

    assert str(raised.value) == "OpenRouter could not be reached."
    assert raised.value.code == "provider_unavailable"
    assert isinstance(raised.value.__cause__, ModelDiscoveryError)


#
# The portfolio
#


def test_an_authorized_model_is_in_the_portfolio_and_marked_in_the_catalog(
    modelled: api.Azathoth,
    location: str,
) -> None:
    entry = modelled.portfolio.add(ALPHA.identifier)

    assert entry.model_dump(exclude={"author", "added_at"}) == {
        "identifier": ALPHA.identifier,
        "provider": "provider-a",
        "model": "example/alpha",
        "content_digest": content_digest(
            ModelPortfolioEntry(provider="provider-a", model="example/alpha")
        ),
        "data_policy": {"retains_data": "unknown", "trains_on_data": "unknown"},
        "receives_restricted": False,
        "command": "azathoth model show provider-a/example/alpha",
    }
    assert entry.added_at is not None
    assert modelled.portfolio.list() == (entry,)
    assert tuple(model.authorized for model in modelled.models.list()) == (True, False)
    assert open_repositories(location).portfolio.entries() == (
        ModelPortfolioEntry(provider="provider-a", model="example/alpha"),
    )


def test_the_portfolio_lists_in_authorization_order(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(BETA.identifier)
    modelled.portfolio.add(ALPHA.identifier)

    assert tuple(entry.identifier for entry in modelled.portfolio.list()) == (
        BETA.identifier,
        ALPHA.identifier,
    )


def test_the_portfolio_is_read_without_reaching_a_provider(
    location: str,
) -> None:
    open_repositories(location).portfolio.save(
        ModelPortfolioEntry(provider="provider-a", model="example/alpha")
    )
    directory = StaticDirectory("provider-a", (ALPHA,))

    with api.Azathoth(open_repositories(location), directories=(directory,)) as instance:
        assert tuple(entry.identifier for entry in instance.portfolio.list()) == (ALPHA.identifier,)

    assert directory.calls == 0


def test_only_an_available_model_can_be_authorized(
    modelled: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        modelled.portfolio.add("provider-a/example/missing")

    assert str(raised.value) == "Model 'provider-a/example/missing' is not currently available."
    assert modelled.portfolio.list() == ()


def test_a_model_is_authorized_once(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)

    with pytest.raises(api.ConflictError) as raised:
        modelled.portfolio.add(ALPHA.identifier)

    assert str(raised.value) == f"Model {ALPHA.identifier!r} is already authorized."
    assert raised.value.code == "conflict"


def test_a_model_is_deauthorized(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)

    removal = modelled.portfolio.remove(ALPHA.identifier)

    assert removal == api.PortfolioRemoval(
        identifier=ALPHA.identifier,
        dependents=(),
        command="azathoth model deauthorize provider-a/example/alpha",
    )
    assert parses(removal.command)
    assert modelled.portfolio.list() == ()


def test_only_an_authorized_model_can_be_deauthorized(
    modelled: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        modelled.portfolio.remove(ALPHA.identifier)

    assert str(raised.value) == f"Model {ALPHA.identifier!r} is not authorized."


def test_a_semantic_judge_is_never_deauthorized_even_by_force(
    modelled: api.Azathoth,
    location: str,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)
    open_repositories(location).judges.add(JudgeEntry(provider="provider-a", model="example/alpha"))

    with pytest.raises(api.ConflictError) as raised:
        modelled.portfolio.remove(ALPHA.identifier, force=True)

    assert str(raised.value) == (
        f"Model {ALPHA.identifier!r} is a semantic judge and was not deauthorized; "
        f"remove it from the rotation first with: azathoth judge remove {ALPHA.identifier}"
    )
    assert tuple(entry.identifier for entry in modelled.portfolio.list()) == (ALPHA.identifier,)


def test_a_model_in_production_is_kept_and_its_dependents_named(
    modelled: api.Azathoth,
    location: str,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)
    open_repositories(location).production_states.set(
        WorkflowProductionState(specification=pinned_workflow(ALPHA.identifier))
    )

    with pytest.raises(api.ModelInUseError) as raised:
        modelled.portfolio.remove(ALPHA.identifier)

    dependent = api.ProductionDependent(
        workflow_id=WORKFLOW_ID,
        workflow_name="summarize",
        steps=(api.ProductionStepUsage(step_id=STEP_ID, role="primary"),),
    )

    assert str(raised.value) == (
        f"Model {ALPHA.identifier!r} is used by active production and was not deauthorized."
    )
    assert raised.value.code == "model_in_use"
    assert raised.value.dependents == (dependent,)
    assert isinstance(raised.value, api.ConflictError)
    assert tuple(entry.identifier for entry in modelled.portfolio.list()) == (ALPHA.identifier,)


def test_forcing_deauthorizes_a_model_in_production_and_names_its_dependents(
    modelled: api.Azathoth,
    location: str,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)
    open_repositories(location).production_states.set(
        WorkflowProductionState(specification=pinned_workflow(ALPHA.identifier))
    )

    removal = modelled.portfolio.remove(ALPHA.identifier, force=True)

    assert tuple(dependent.workflow_id for dependent in removal.dependents) == (WORKFLOW_ID,)
    assert removal.command == "azathoth model deauthorize provider-a/example/alpha --force"
    assert parses(removal.command)
    assert modelled.portfolio.list() == ()


def test_forcing_without_dependents_is_an_ordinary_removal(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)

    removal = modelled.portfolio.remove(ALPHA.identifier, force=True)

    assert removal.dependents == ()
    assert removal.command == "azathoth model deauthorize provider-a/example/alpha"


#
# The models a step's needs match
#


def matching(
    instance: api.Azathoth,
    **requirements: JsonValue,
) -> tuple[str, ...]:
    """Return the identifiers of the portfolio's models that meet the requirements."""

    return tuple(model.identifier for model in instance.models.matching(requirements))


def test_the_portfolios_models_match_in_the_order_a_run_tries_them(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(BETA.identifier)
    modelled.portfolio.add(ALPHA.identifier)

    matched = modelled.models.matching({})

    assert tuple(model.identifier for model in matched) == (BETA.identifier, ALPHA.identifier)
    assert all(model.authorized for model in matched)
    assert matched[1] == modelled.models.get(ALPHA.identifier)


def test_a_served_model_outside_the_portfolio_never_matches(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)

    assert matching(modelled) == (ALPHA.identifier,)


def test_a_model_matches_only_what_it_meets(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(BETA.identifier)
    modelled.portfolio.add(ALPHA.identifier)

    assert matching(modelled, required_capabilities=["vision"]) == (ALPHA.identifier,)
    assert matching(modelled, required_input_modalities=["image"]) == (ALPHA.identifier,)
    assert matching(modelled, required_output_modalities=["image"]) == ()
    assert matching(modelled, minimum_context_window_tokens=128_000) == (ALPHA.identifier,)
    assert matching(modelled, minimum_context_window_tokens=128_001) == ()
    assert matching(modelled, minimum_output_tokens=16_384) == (ALPHA.identifier,)
    assert matching(modelled, maximum_input_usd_per_million_tokens=1.25) == (ALPHA.identifier,)
    assert matching(modelled, maximum_input_usd_per_million_tokens=1.0) == ()
    assert matching(modelled, maximum_output_usd_per_million_tokens=4.99) == ()
    assert matching(modelled, require_known_pricing=True) == (ALPHA.identifier,)


@pytest.mark.parametrize(
    ("requirements", "message"),
    [
        ({"fast": True}, "Unknown model requirement 'fast'."),
        (
            {"required_capabilities": ["telepathy"]},
            "Model requirement 'required_capabilities' is not valid: ",
        ),
        (
            {"minimum_context_window_tokens": 0},
            "Model requirement 'minimum_context_window_tokens' is not valid: "
            "Input should be greater than 0",
        ),
    ],
)
def test_requirements_that_are_not_valid_are_refused(
    modelled: api.Azathoth,
    requirements: dict[str, JsonValue],
    message: str,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)

    with pytest.raises(api.InvalidArgumentError) as raised:
        modelled.models.matching(requirements)

    assert str(raised.value).startswith(message)


def test_a_closed_instance_refuses_models_and_the_portfolio(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    for call in (
        opened.models.list,
        opened.portfolio.list,
        lambda: opened.models.matching({}),
    ):
        with pytest.raises(api.InstanceClosedError):
            call()


#
# Provider settings
#


def test_provider_settings_read_the_variables_the_cli_reads() -> None:
    assert api.OPENROUTER_API_KEY_VARIABLE == OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE
    assert api.BEDROCK_VARIABLES == BEDROCK_ENVIRONMENT_VARIABLES


def test_provider_settings_come_from_the_environment() -> None:
    settings = api.ProviderSettings.from_environment(
        {
            "OPENROUTER_API_KEY": "sk-or-example",
            "AZATHOTH_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
            "UNRELATED": "ignored",
        }
    )

    assert settings.openrouter_api_key == SecretStr("sk-or-example")
    assert settings.bedrock_environment == (
        ("AZATHOTH_BEDROCK", "1"),
        ("AWS_REGION", "us-east-1"),
    )
    assert "sk-or-example" not in repr(settings)


def test_bedrock_variables_are_kept_only_while_bedrock_is_on() -> None:
    settings = api.ProviderSettings.from_environment({"AWS_REGION": "us-east-1"})

    assert settings == api.ProviderSettings()


def test_an_empty_key_turns_openrouter_off() -> None:
    settings = api.ProviderSettings.from_environment({"OPENROUTER_API_KEY": ""})

    assert settings.openrouter_api_key is None


def test_opening_with_providers_reaches_none_until_models_are_asked_for(
    location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_boto3() -> NoReturn:
        raise BedrockUnavailableError()

    monkeypatch.setattr("azathoth.api.providers.boto3_driver", no_boto3)

    settings = api.ProviderSettings(bedrock_environment=(("AZATHOTH_BEDROCK", "1"),))

    with api.open(location, providers=settings) as instance:
        assert instance.portfolio.list() == ()

        with pytest.raises(api.ProviderConfigurationError) as raised:
            instance.models.list()

    assert str(raised.value) == str(BedrockUnavailableError())
    assert raised.value.code == "provider_configuration"


def test_an_authorized_model_records_who_added_it(
    location: str,
) -> None:
    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory("provider-a", (ALPHA,)),),
        author="Eris <eris@example.com>",
    ) as instance:
        instance.portfolio.add(ALPHA.identifier)

    provenance = open_repositories(location).portfolio.provenance(ALPHA.identifier)

    assert provenance is not None
    assert provenance.author == Author(name="Eris", email="eris@example.com")


def test_a_model_is_not_authorized_when_who_adds_it_cannot_be_told(
    modelled: api.Azathoth,
    location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTHOR_VARIABLE, "Eris <eris>")

    with pytest.raises(api.InvalidAuthorError):
        modelled.portfolio.add(ALPHA.identifier)

    assert open_repositories(location).portfolio.entries() == ()


def test_the_portfolio_lists_who_authorized_each_model_and_when(
    location: str,
) -> None:
    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory("provider-a", (ALPHA,)),),
        author="Eris",
    ) as instance:
        added = instance.portfolio.add(ALPHA.identifier)

        (listed,) = instance.portfolio.list()

    provenance = open_repositories(location).portfolio.provenance(ALPHA.identifier)

    assert provenance is not None
    assert listed == added
    assert listed.author == api.Author(name="Eris", email=None)
    assert listed.added_at == provenance.added_at
    assert listed.content_digest == provenance.content_digest


def test_a_model_authorized_without_an_author_lists_none(
    location: str,
) -> None:
    open_repositories(location).portfolio.save(
        ModelPortfolioEntry(provider="provider-a", model="example/alpha"),
    )

    with api.Azathoth(open_repositories(location), directories=()) as instance:
        (listed,) = instance.portfolio.list()

    assert listed.author is None
    assert listed.added_at is not None
