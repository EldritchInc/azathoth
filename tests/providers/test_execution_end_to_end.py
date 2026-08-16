"""End-to-end tests for deterministic model request execution."""

import asyncio

from azathoth.providers import (
    DeterministicLanguageModel,
    ModelExecutor,
    ModelRequest,
    ModelResponse,
    Prompt,
)


def create_request() -> ModelRequest:
    """Create a deterministic model request."""

    return ModelRequest(
        prompt=Prompt(
            text="Classify this text as positive or negative.",
        ),
    )


def create_language_model() -> DeterministicLanguageModel:
    """Create a deterministic language model."""

    return DeterministicLanguageModel(
        provider="deterministic",
        model="classifier-small",
        response_text="positive",
    )


def test_model_request_executes_end_to_end() -> None:
    executor = ModelExecutor()
    request = create_request()
    language_model = create_language_model()

    response = asyncio.run(
        executor.execute(
            request,
            language_model,
        )
    )

    assert response.text == "positive"
    assert response.provider == "deterministic"
    assert response.model == "classifier-small"
    assert response.prompt_tokens == 7
    assert response.completion_tokens == 1
    assert response.total_tokens == 8
    assert response.latency_ms == 0
    assert response.estimated_cost_usd == 0.0


def test_model_request_round_trips_before_execution() -> None:
    request = create_request()

    restored_request = ModelRequest.model_validate_json(
        request.model_dump_json(),
    )

    response = asyncio.run(
        ModelExecutor().execute(
            restored_request,
            create_language_model(),
        )
    )

    assert restored_request == request
    assert response.text == "positive"


def test_model_response_round_trips_after_execution() -> None:
    response = asyncio.run(
        ModelExecutor().execute(
            create_request(),
            create_language_model(),
        )
    )

    restored_response = ModelResponse.model_validate_json(
        response.model_dump_json(),
    )

    assert restored_response == response
    assert restored_response.provider == "deterministic"
    assert restored_response.model == "classifier-small"
    assert restored_response.total_tokens == 8


def test_repeated_request_execution_is_deterministic() -> None:
    executor = ModelExecutor()
    request = create_request()
    language_model = create_language_model()

    first = asyncio.run(
        executor.execute(
            request,
            language_model,
        )
    )
    second = asyncio.run(
        executor.execute(
            request,
            language_model,
        )
    )

    assert first == second


def test_complete_model_execution_lifecycle_round_trips() -> None:
    request = create_request()

    restored_request = ModelRequest.model_validate_json(
        request.model_dump_json(),
    )

    response = asyncio.run(
        ModelExecutor().execute(
            restored_request,
            create_language_model(),
        )
    )

    restored_response = ModelResponse.model_validate_json(
        response.model_dump_json(),
    )

    assert restored_request == request
    assert restored_response == response
    assert restored_response.text == "positive"
    assert restored_response.provider == "deterministic"
    assert restored_response.model == "classifier-small"
    assert restored_response.prompt_tokens == 7
    assert restored_response.completion_tokens == 1
    assert restored_response.total_tokens == 8
    assert restored_response.latency_ms == 0
    assert restored_response.estimated_cost_usd == 0.0
