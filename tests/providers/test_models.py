"""Tests for provider request and response models."""

import pytest
from pydantic import ValidationError

from azathoth.providers import (
    ModelRequest,
    ModelResponse,
    Prompt,
)


def test_prompt_round_trips() -> None:
    prompt = Prompt(
        text="Hello world",
    )

    restored = Prompt.model_validate_json(prompt.model_dump_json())

    assert restored == prompt


def test_model_request_records_prompt() -> None:
    prompt = Prompt(
        text="Classify this text.",
    )
    request = ModelRequest(
        prompt=prompt,
    )

    assert request.prompt == prompt
    assert request.temperature is None
    assert request.max_output_tokens is None


def test_model_request_records_generation_parameters() -> None:
    request = ModelRequest(
        prompt=Prompt(
            text="Classify this text.",
        ),
        temperature=0.0,
        max_output_tokens=25,
    )

    assert request.temperature == 0.0
    assert request.max_output_tokens == 25


def test_model_request_rejects_negative_temperature() -> None:
    with pytest.raises(ValidationError):
        ModelRequest(
            prompt=Prompt(
                text="Classify this text.",
            ),
            temperature=-0.1,
        )


def test_model_request_rejects_non_positive_max_output_tokens() -> None:
    with pytest.raises(ValidationError):
        ModelRequest(
            prompt=Prompt(
                text="Classify this text.",
            ),
            max_output_tokens=0,
        )


def test_model_request_is_immutable() -> None:
    request = ModelRequest(
        prompt=Prompt(
            text="Classify this text.",
        ),
    )

    with pytest.raises(ValidationError):
        request.temperature = 0.5


def test_model_request_round_trips() -> None:
    request = ModelRequest(
        prompt=Prompt(
            text="Classify this text.",
        ),
        temperature=0.0,
        max_output_tokens=25,
    )

    restored = ModelRequest.model_validate_json(
        request.model_dump_json(),
    )

    assert restored == request


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

    restored = ModelResponse.model_validate_json(
        response.model_dump_json(),
    )

    assert restored == response
    assert response.provider == "test"
    assert response.model == "stub"
    assert response.total_tokens == 12
    assert response.latency_ms == 15
    assert response.estimated_cost_usd == 0.0001


def test_prompt_is_immutable() -> None:
    prompt = Prompt(
        text="Hello",
    )

    with pytest.raises(ValidationError):
        prompt.text = "Changed"


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

    with pytest.raises(ValidationError):
        response.text = "Changed"
