"""Tests for the deterministic language model."""

import asyncio

from azathoth.providers import (
    DeterministicLanguageModel,
    Prompt,
)


def test_returns_configured_response() -> None:
    model = DeterministicLanguageModel(
        response_text="classified",
    )

    response = asyncio.run(
        model.complete(
            Prompt(
                text="classify this",
            )
        )
    )

    assert response.text == "classified"


def test_records_provider_metadata() -> None:
    model = DeterministicLanguageModel(
        provider="test",
        model="tiny",
    )

    response = asyncio.run(
        model.complete(
            Prompt(
                text="hello",
            )
        )
    )

    assert response.provider == "test"
    assert response.model == "tiny"


def test_counts_prompt_tokens() -> None:
    model = DeterministicLanguageModel()

    response = asyncio.run(
        model.complete(
            Prompt(
                text="one two three four",
            )
        )
    )

    assert response.prompt_tokens == 4


def test_counts_completion_tokens() -> None:
    model = DeterministicLanguageModel(
        response_text="one two",
    )

    response = asyncio.run(
        model.complete(
            Prompt(
                text="hello",
            )
        )
    )

    assert response.completion_tokens == 2
    assert response.total_tokens == 3


def test_reports_zero_cost() -> None:
    model = DeterministicLanguageModel()

    response = asyncio.run(
        model.complete(
            Prompt(
                text="hello",
            )
        )
    )

    assert response.latency_ms == 0
    assert response.estimated_cost_usd == 0.0


def test_multiple_calls_are_deterministic() -> None:
    model = DeterministicLanguageModel(
        response_text="always",
    )

    prompt = Prompt(
        text="same prompt",
    )

    first = asyncio.run(model.complete(prompt))
    second = asyncio.run(model.complete(prompt))

    assert first == second
