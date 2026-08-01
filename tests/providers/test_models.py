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
    )

    restored = ModelResponse.model_validate_json(response.model_dump_json())

    assert restored == response


def test_prompt_is_immutable() -> None:
    prompt = Prompt(text="Hello")

    try:
        prompt.text = "Changed"
    except ValidationError:
        pass
    else:
        raise AssertionError("Prompt should be immutable.")


def test_model_response_is_immutable() -> None:
    response = ModelResponse(text="Hello")

    try:
        response.text = "Changed"
    except ValidationError:
        pass
    else:
        raise AssertionError("ModelResponse should be immutable.")
