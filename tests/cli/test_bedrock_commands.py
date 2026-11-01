"""Tests for the CLI over Amazon Bedrock: configuration, composition and failures (ADR 0103).

Bedrock is reached through a fake client, put in place of boto3's by
replacing the bootstrap's driver, so these tests need no network, no AWS
account and no boto3.
"""

import asyncio
import io
import json
import sys
from pathlib import Path

import pytest

from azathoth.cli import CliRuntimeConfiguration, load_runtime, main, run_job_request
from azathoth.cli import bootstrap as cli_bootstrap
from azathoth.providers import (
    MISSING_BEDROCK_EXTRA_MESSAGE,
    MISSING_REGION_MESSAGE,
    BedrockClientError,
    BedrockConfiguration,
    BedrockDriver,
    ModelDiscoveryError,
    ModelPricing,
    Prompt,
    ProviderModel,
    SQLiteModelPortfolioRepository,
    SQLiteProviderModelObservationRepository,
)
from tests.providers.fake_bedrock import FakeBedrockClient, foundation_model, inference_profile

NOVA_PRO = "amazon.nova-pro-v1:0"

CLAUDE = "anthropic.claude-sonnet-4-20250514-v1:0"

US_CLAUDE = "us.anthropic.claude-sonnet-4-20250514-v1:0"

AWS_SECRET = "aws-secret-access-key"

PRICING = {
    "version": 1,
    "models": {
        NOVA_PRO: {
            "input_usd_per_million_tokens": 0.8,
            "output_usd_per_million_tokens": 3.2,
        },
    },
}

CONVERSE_REPLY = {
    "output": {"message": {"role": "assistant", "content": [{"text": "4"}]}},
    "stopReason": "end_turn",
    "usage": {"inputTokens": 1_000, "outputTokens": 250, "totalTokens": 1_250},
    "metrics": {"latencyMs": 412},
}


class FakeOpenRouterModelDirectory:
    """Report one OpenRouter model, so both providers can be composed."""

    def __init__(
        self,
        configuration: object,
    ) -> None:
        self._configuration = configuration

    @property
    def provider(
        self,
    ) -> str:
        return "openrouter"

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        return (
            ProviderModel(
                provider="openrouter",
                model="example/model",
                display_name="Example Model",
            ),
        )

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        return None


@pytest.fixture
def client() -> FakeBedrockClient:
    """Return a fake region offering one on-demand model and one inference profile."""

    return FakeBedrockClient(
        foundation_models=[
            foundation_model(NOVA_PRO, name="Nova Pro"),
            foundation_model(
                CLAUDE, name="Claude Sonnet 4", inference_types=("INFERENCE_PROFILE",)
            ),
        ],
        inference_profile_pages=[[inference_profile(US_CLAUDE, CLAUDE, name="US Claude Sonnet 4")]],
        replies={NOVA_PRO: [CONVERSE_REPLY]},
    )


@pytest.fixture
def configurations(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeBedrockClient,
) -> list[BedrockConfiguration]:
    """Replace the bootstrap's driver with one over the fake client.

    It records every configuration it makes a client for.
    """

    made: list[BedrockConfiguration] = []

    def make(
        configuration: BedrockConfiguration,
    ) -> FakeBedrockClient:
        made.append(configuration)

        return client

    monkeypatch.setattr(
        cli_bootstrap,
        "_bedrock_driver",
        lambda: BedrockDriver(region=lambda: None, client=make),
    )

    return made


@pytest.fixture
def environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Turn Bedrock on in us-east-1 over a fresh database, and return its pricing file."""

    pricing = tmp_path / "bedrock-pricing.json"
    pricing.write_text(json.dumps(PRICING), encoding="utf-8")

    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))
    monkeypatch.setenv("AZATHOTH_BEDROCK", "1")
    monkeypatch.setenv("AZATHOTH_BEDROCK_PRICING", str(pricing))
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    return pricing


def cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one command, and return its status, stdout and stderr."""

    code = main(arguments)
    captured = capsys.readouterr()

    return code, captured.out, captured.err


# Configuration


def test_bedrock_is_off_by_default() -> None:
    configuration = CliRuntimeConfiguration.from_environment({"AWS_REGION": "us-east-1"})

    assert configuration.bedrock_environment == ()
    assert not configuration.bedrock_enabled


def test_bedrock_on_keeps_only_its_own_variables_and_no_credentials() -> None:
    configuration = CliRuntimeConfiguration.from_environment(
        {
            "AZATHOTH_BEDROCK": "yes",
            "AZATHOTH_BEDROCK_PRICING": "/etc/azathoth/pricing.json",
            "AWS_REGION": "us-east-1",
            "AWS_DEFAULT_REGION": "us-west-2",
            "AWS_SECRET_ACCESS_KEY": AWS_SECRET,
            "AWS_PROFILE": "production",
        }
    )

    assert configuration.bedrock_enabled
    assert dict(configuration.bedrock_environment) == {
        "AZATHOTH_BEDROCK": "yes",
        "AZATHOTH_BEDROCK_PRICING": "/etc/azathoth/pricing.json",
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-west-2",
    }
    assert AWS_SECRET not in repr(configuration)


# Composition


@pytest.mark.usefixtures("environment")
def test_the_runtime_holds_the_regions_bedrock_models_at_their_prices(
    configurations: list[BedrockConfiguration],
) -> None:
    runtime = load_runtime(CliRuntimeConfiguration.from_environment())

    assert runtime.models.identifiers == (f"bedrock/{NOVA_PRO}", f"bedrock/{US_CLAUDE}")
    assert runtime.language_models.identifiers == runtime.models.identifiers

    nova_pro = runtime.models.get(f"bedrock/{NOVA_PRO}")

    assert nova_pro is not None
    assert nova_pro.pricing == ModelPricing(
        input_usd_per_million_tokens=0.8,
        output_usd_per_million_tokens=3.2,
    )
    assert {configuration.region for configuration in configurations} == {"us-east-1"}


@pytest.mark.usefixtures("environment", "configurations")
def test_a_composed_bedrock_model_completes_through_converse(
    client: FakeBedrockClient,
) -> None:
    runtime = load_runtime(CliRuntimeConfiguration.from_environment())

    model = runtime.language_models.get(f"bedrock/{NOVA_PRO}")

    assert model is not None

    response = asyncio.run(model.complete(Prompt(text="How many?")))

    assert response.text == "4"
    assert response.estimated_cost_usd == pytest.approx(0.0016)
    assert ("converse", NOVA_PRO, "How many?") in client.calls


@pytest.mark.usefixtures("environment", "configurations")
def test_bedrock_observations_are_recorded(
    tmp_path: Path,
) -> None:
    load_runtime(CliRuntimeConfiguration.from_environment())

    repository = SQLiteProviderModelObservationRepository(tmp_path / "azathoth.db")

    assert [observation.identifier for observation in repository.observations()] == [
        f"bedrock/{NOVA_PRO}",
        f"bedrock/{US_CLAUDE}",
    ]


@pytest.mark.usefixtures("environment", "configurations")
def test_openrouter_and_bedrock_are_composed_together_openrouter_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr(cli_bootstrap, "OpenRouterModelDirectory", FakeOpenRouterModelDirectory)

    runtime = load_runtime(CliRuntimeConfiguration.from_environment())

    assert runtime.models.identifiers == (
        "openrouter/example/model",
        f"bedrock/{NOVA_PRO}",
        f"bedrock/{US_CLAUDE}",
    )
    assert runtime.language_models.identifiers == runtime.models.identifiers


def test_bedrock_off_makes_no_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configurations: list[BedrockConfiguration],
) -> None:
    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("AZATHOTH_BEDROCK", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    runtime = load_runtime(CliRuntimeConfiguration.from_environment())

    assert runtime.models.identifiers == ()
    assert configurations == []


# Commands


@pytest.mark.usefixtures("environment", "configurations")
def test_model_list_shows_the_bedrock_models(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli(capsys, "model", "list") == (
        0,
        f"bedrock/{NOVA_PRO}  Nova Pro\nbedrock/{US_CLAUDE}  US Claude Sonnet 4\n",
        "",
    )


@pytest.mark.usefixtures("environment", "configurations")
def test_a_bedrock_model_is_authorized_by_its_identifier(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli(capsys, "model", "authorize", f"bedrock/{US_CLAUDE}") == (
        0,
        f"Authorized model bedrock/{US_CLAUDE}.\n",
        "",
    )

    (entry,) = SQLiteModelPortfolioRepository(tmp_path / "azathoth.db").entries()

    assert (entry.provider, entry.model) == ("bedrock", US_CLAUDE)


@pytest.mark.usefixtures("environment", "configurations")
def test_an_unpriced_model_shows_its_price_as_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = cli(capsys, "model", "show", f"bedrock/{US_CLAUDE}")

    assert code == 0
    assert "Input Price: unknown\nOutput Price: unknown\n" in out


# Failures


@pytest.mark.usefixtures("environment")
def test_bedrock_on_without_the_extra_says_what_to_install(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    assert cli(capsys, "model", "list") == (1, "", f"{MISSING_BEDROCK_EXTRA_MESSAGE}\n")


@pytest.mark.usefixtures("environment", "configurations")
def test_bedrock_on_without_a_region_says_so(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("AWS_REGION")
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    assert cli(capsys, "model", "list") == (1, "", f"{MISSING_REGION_MESSAGE}\n")


@pytest.mark.usefixtures("configurations")
def test_an_unusable_pricing_document_is_refused(
    environment: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment.write_text('{"version": 1, "model": {}}', encoding="utf-8")

    assert cli(capsys, "model", "list") == (
        1,
        "",
        f"AZATHOTH_BEDROCK_PRICING {environment} is not a valid Bedrock pricing document: "
        "model: Extra inputs are not permitted.\n",
    )


@pytest.mark.usefixtures("environment", "configurations")
def test_bedrock_that_cannot_be_discovered_fails_the_command_in_one_line(
    client: FakeBedrockClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client.listing_error = BedrockClientError("AccessDeniedException", "Not authorized.")

    assert cli(capsys, "model", "list") == (
        1,
        "",
        "Bedrock model discovery request failed: AccessDeniedException: Not authorized.\n",
    )


@pytest.mark.usefixtures("environment")
def test_a_command_that_composes_no_runtime_never_reaches_bedrock(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    assert cli(capsys, "tool", "list") == (0, "", "")


@pytest.mark.usefixtures("environment", "configurations")
def test_a_job_whose_bedrock_cannot_be_discovered_prints_no_result(
    client: FakeBedrockClient,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    client.listing_error = BedrockClientError("ThrottlingException", "Slow down.")

    source = tmp_path / "request.json"
    source.write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "bedrock-undiscovered-1",
                "workflow_id": "a1000000-0000-4000-8000-000000000002",
                "input": {"value": "the old ones wait"},
            }
        ),
        encoding="utf-8",
    )

    assert cli(capsys, "job", "run", str(source)) == (
        1,
        "",
        "Bedrock model discovery request failed: ThrottlingException: Slow down.\n",
    )


@pytest.mark.usefixtures("environment", "configurations")
def test_a_job_over_stdin_whose_bedrock_cannot_be_discovered_raises_to_main(
    client: FakeBedrockClient,
) -> None:
    client.listing_error = BedrockClientError("ThrottlingException", "Slow down.")

    request = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": "bedrock-undiscovered-2",
        "workflow_id": "a1000000-0000-4000-8000-000000000002",
        "input": {"value": "the old ones wait"},
    }

    with pytest.raises(ModelDiscoveryError, match="ThrottlingException"):
        run_job_request("-", stdin=io.BytesIO(json.dumps(request).encode("utf-8")))


# Running a workflow on Bedrock


SIMPLE_PROMPT = Path(__file__).parents[2] / "examples" / "workflows" / "simple-prompt.json"

SIMPLE_PROMPT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.usefixtures("environment", "configurations")
def test_a_prompt_workflow_runs_on_an_authorized_bedrock_model_at_its_price(
    client: FakeBedrockClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for arguments in (
        ("workflow", "import", str(SIMPLE_PROMPT)),
        ("model", "authorize", f"bedrock/{NOVA_PRO}"),
    ):
        code, _, err = cli(capsys, *arguments)

        assert code == 0, err

    code, out, err = cli(
        capsys,
        "workflow",
        "run",
        SIMPLE_PROMPT_ID,
        "--input",
        '"How many words are in the old ones wait?"',
        "--output",
        "jsonl",
    )

    assert code == 0, err
    assert ("converse", NOVA_PRO) in [call[:2] for call in client.calls]

    (record,) = [json.loads(line) for line in out.splitlines()]

    assert record["type"] == "result"
    assert record["value"] == "4"

    code, shown, err = cli(capsys, "run", "show", record["run_id"])

    assert code == 0, err
    assert f"Model: {NOVA_PRO}" in shown
    assert "Estimated Cost: $0.001600" in shown


@pytest.mark.usefixtures("environment", "configurations")
def test_a_job_runs_a_promoted_workflow_on_bedrock(
    client: FakeBedrockClient,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    for arguments in (
        ("workflow", "import", str(SIMPLE_PROMPT)),
        ("model", "authorize", f"bedrock/{NOVA_PRO}"),
        ("workflow", "promote", SIMPLE_PROMPT_ID),
    ):
        code, _, err = cli(capsys, *arguments)

        assert code == 0, (arguments, err)

    source = tmp_path / "request.json"
    source.write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "bedrock-job-1",
                "workflow_id": SIMPLE_PROMPT_ID,
                "input": {"value": "How many words are in the old ones wait?"},
            }
        ),
        encoding="utf-8",
    )

    code, out, err = cli(capsys, "job", "run", str(source))

    assert code == 0, err

    result = json.loads(out)

    assert result["status"] == "succeeded"
    assert result["result"] == {"result": "4"}
    assert ("converse", NOVA_PRO) in [call[:2] for call in client.calls]
