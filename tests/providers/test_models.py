"""Tests for provider request and response models."""

from pydantic import ValidationError

from azathoth.providers import (
    ModelResponse,
    Prompt,
)


def test_prompt_round_trips() -> None:
    prompt = Prompt(
        text="Hello world",
    )

    restored = Prompt.model_validate_json(prompt.model_dump_json())

    assert restored == prompt


def test_model_response_round_trips() -> None:
    response = ModelResponse(
        text="Hello human",
        provider="test",
        model="stub",
        prompt_tokens=10,
        completion_tokens=2,
        total_tokens=12,
        latency_ms=15,
        estimated_cost_usd=0.0001,
    )

    restored = ModelResponse.model_validate_json(response.model_dump_json())

    assert restored == response
    assert response.provider == "test"
    assert response.model == "stub"
    assert response.total_tokens == 12
    assert response.latency_ms == 15
    assert response.estimated_cost_usd == 0.0001


def test_prompt_is_immutable() -> None:
    prompt = Prompt(text="Hello")

    try:
        prompt.text = "Changed"
    except ValidationError:
        pass
    else:
        raise AssertionError("Prompt should be immutable.")


def test_model_response_is_immutable() -> None:
    response = ModelResponse(
        text="Hello",
        provider="test",
        model="stub",
        prompt_tokens=10,
        completion_tokens=2,
        total_tokens=12,
        latency_ms=15,
        estimated_cost_usd=0.0001,
    )

    try:
        response.text = "Changed"
    except ValidationError:
        pass
    else:
        raise AssertionError("ModelResponse should be immutable.")
