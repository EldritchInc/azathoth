"""Tests for prompt strategies whose replies are parsed as JSON."""

import asyncio
import json
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    PortfolioModelSelection,
    PromptOutputFormat,
    PromptOutputFormatError,
    PromptStrategy,
    PromptStrategySpec,
    PromptTemplate,
    generate_context_prompt_candidates,
    generate_prompt_candidates,
    parse_json_reply,
)
from azathoth.prompting.execution import execute_prompt
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from tests.prompting.test_context_candidates import (
    FIRST_IDENTIFIER,
    create_catalog,
    create_portfolio,
)

STRATEGY_ID = UUID("c5000000-0000-4000-8000-000000000001")

JSON_REPLY = '{"category": "billing", "urgent": true}'

PARSED_REPLY: JsonValue = {
    "category": "billing",
    "urgent": True,
}


def metadata() -> StrategyMetadata:
    """Create deterministic strategy metadata."""

    return StrategyMetadata(
        id=STRATEGY_ID,
        name="Triage ticket",
        description="Classify one support ticket.",
        version="1.0.0",
    )


def prompt_specification(
    output_format: PromptOutputFormat = PromptOutputFormat.TEXT,
) -> PromptStrategySpec:
    """Create a fixed-prompt specification with the given output format."""

    return PromptStrategySpec(
        metadata=metadata(),
        prompt=Prompt(text="Triage this ticket."),
        model_selection=PortfolioModelSelection(requirements=ModelRequirements()),
        output_format=output_format,
    )


def context_specification(
    output_format: PromptOutputFormat = PromptOutputFormat.TEXT,
) -> ContextPromptStrategySpec:
    """Create a context-rendered specification with the given output format."""

    return ContextPromptStrategySpec(
        metadata=metadata(),
        template=PromptTemplate(text="Triage this ticket."),
        model_selection=PortfolioModelSelection(requirements=ModelRequirements()),
        output_format=output_format,
    )


def json_registry() -> LanguageModelRegistry:
    """Create one executable model that replies with JSON."""

    return LanguageModelRegistry(
        models={
            FIRST_IDENTIFIER: DeterministicLanguageModel(
                provider="provider-a",
                model="classifier",
                response_text=JSON_REPLY,
            ),
        }
    )


def execute(
    reply: str,
    output_format: PromptOutputFormat,
) -> JsonValue:
    """Execute one prompt against a model returning the given reply."""

    outcome = asyncio.run(
        execute_prompt(
            prompt=Prompt(text="Triage this ticket."),
            language_model=DeterministicLanguageModel(response_text=reply),
            model_binding=None,
            output_format=output_format,
            strategy_name="Triage ticket",
        )
    )

    return outcome.output


@pytest.mark.parametrize(
    ("reply", "parsed"),
    [
        pytest.param(JSON_REPLY, PARSED_REPLY, id="object"),
        pytest.param(f"\n  {JSON_REPLY}\n", PARSED_REPLY, id="surrounding-whitespace"),
        pytest.param(f"```json\n{JSON_REPLY}\n```", PARSED_REPLY, id="json-fence"),
        pytest.param(f"```\n{JSON_REPLY}\n```\n", PARSED_REPLY, id="bare-fence"),
        pytest.param('["Ada", "Grace"]', ["Ada", "Grace"], id="list"),
        pytest.param('"plain"', "plain", id="string"),
        pytest.param("18", 18, id="number"),
    ],
)
def test_json_reply_parses_any_json_value(
    reply: str,
    parsed: JsonValue,
) -> None:
    assert parse_json_reply(reply) == parsed


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param("Sure! Here it is: {}", id="prose"),
        pytest.param("```json\n{}\n```\n```json\n{}\n```", id="two-fences"),
        pytest.param("", id="empty"),
    ],
)
def test_json_reply_rejects_anything_else(
    reply: str,
) -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_json_reply(reply)


def test_json_output_returns_the_parsed_reply() -> None:
    assert execute(f"```json\n{JSON_REPLY}\n```", PromptOutputFormat.JSON) == PARSED_REPLY


def test_text_output_returns_the_reply_unchanged() -> None:
    assert execute(JSON_REPLY, PromptOutputFormat.TEXT) == JSON_REPLY


def test_execute_prompt_defaults_to_text_output() -> None:
    outcome = asyncio.run(
        execute_prompt(
            prompt=Prompt(text="Triage this ticket."),
            language_model=DeterministicLanguageModel(response_text=JSON_REPLY),
            model_binding=None,
        )
    )

    assert outcome.output == JSON_REPLY


def test_invalid_json_reply_names_the_strategy() -> None:
    with pytest.raises(PromptOutputFormatError) as raised:
        execute("Sure! Here it is.", PromptOutputFormat.JSON)

    assert str(raised.value) == (
        "Prompt strategy 'Triage ticket' replied with invalid JSON: Expecting value."
    )


@pytest.mark.parametrize(
    "specification",
    [
        pytest.param(prompt_specification(), id="prompt"),
        pytest.param(context_specification(), id="context-prompt"),
    ],
)
def test_specifications_default_to_text_and_serialize_without_it(
    specification: PromptStrategySpec | ContextPromptStrategySpec,
) -> None:
    assert specification.output_format == PromptOutputFormat.TEXT
    assert "output_format" not in specification.model_dump()
    assert "output_format" not in json.loads(specification.model_dump_json())


@pytest.mark.parametrize(
    "specification",
    [
        pytest.param(prompt_specification(PromptOutputFormat.JSON), id="prompt"),
        pytest.param(context_specification(PromptOutputFormat.JSON), id="context-prompt"),
    ],
)
def test_json_output_format_serializes_and_round_trips(
    specification: PromptStrategySpec | ContextPromptStrategySpec,
) -> None:
    document = json.loads(specification.model_dump_json())

    assert document["output_format"] == "json"
    assert type(specification).model_validate(document) == specification


def test_specification_saved_before_output_formats_decodes_as_text() -> None:
    document = json.loads(context_specification(PromptOutputFormat.JSON).model_dump_json())

    del document["output_format"]

    assert (
        ContextPromptStrategySpec.model_validate(document).output_format == PromptOutputFormat.TEXT
    )


def test_prompt_candidates_carry_the_output_format() -> None:
    candidates = generate_prompt_candidates(
        specification=prompt_specification(PromptOutputFormat.JSON),
        catalog=create_catalog(),
        registry=json_registry(),
        portfolio=create_portfolio(),
    )

    assert len(candidates) == 1

    candidate = candidates[0]

    assert isinstance(candidate, PromptStrategy)
    assert candidate.output_format == PromptOutputFormat.JSON
    assert asyncio.run(candidate.run(Context())).output == PARSED_REPLY


def test_context_prompt_candidates_carry_the_output_format() -> None:
    candidates = generate_context_prompt_candidates(
        specification=context_specification(PromptOutputFormat.JSON),
        catalog=create_catalog(),
        registry=json_registry(),
        portfolio=create_portfolio(),
    )

    assert len(candidates) == 1

    candidate = candidates[0]

    assert isinstance(candidate, ContextPromptStrategy)
    assert candidate.output_format == PromptOutputFormat.JSON
    assert asyncio.run(candidate.run(Context())).output == PARSED_REPLY
