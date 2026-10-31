"""Tests for the idempotency recorded with production invocations (ADR 0097)."""

import asyncio
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.cli.production import invoke_active_production_workflow
from azathoth.context import Context
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    IdempotencyKeyInUseError,
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    InvocationIdempotency,
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    create_production_invocation,
    invoke_production_workflow,
    validate_idempotency_key,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNDEPLOYED_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

INVOCATION_ID = UUID("55555555-5555-5555-5555-555555555555")

DIGEST = "a" * 64

OTHER_DIGEST = "b" * 64

KEY = "order-4711-review"

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


def idempotency(
    key: str = KEY,
    request_digest: str = DIGEST,
) -> InvocationIdempotency:
    """Create one invocation idempotency record."""

    return InvocationIdempotency(
        key=key,
        request_digest=request_digest,
    )


def create_state() -> WorkflowProductionState:
    """Create deterministic active production state."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="idempotent-production",
                description="Exercise idempotent production invocation.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="idempotent-production-prompt",
                            description="Exercise idempotent production invocation.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Process the production request.",
                        ),
                        model_selection=PRIMARY,
                    ),
                ),
            ),
        )
    )


def create_catalog() -> ModelCatalog:
    """Create current production model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=PRIMARY.provider,
                model=PRIMARY.model,
                display_name=PRIMARY.identifier,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable production model registry."""

    return LanguageModelRegistry(
        {
            PRIMARY.identifier: DeterministicLanguageModel(
                provider=PRIMARY.provider,
                model=PRIMARY.model,
            ),
        }
    )


# Keys and digests


@pytest.mark.parametrize(
    "key",
    [
        "k",
        KEY,
        "x" * MAX_IDEMPOTENCY_KEY_LENGTH,
        "order 4711 / review: ü ✓",
        "123e4567-e89b-12d3-a456-426614174000",
    ],
)
def test_valid_keys_are_accepted(
    key: str,
) -> None:
    assert validate_idempotency_key(key) == key
    assert idempotency(key=key).key == key


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("", "must not be empty"),
        ("x" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1), "at most 255 characters; got 256"),
        ("order\n4711", "must not hold control characters"),
        ("order\t4711", "must not hold control characters"),
        ("order\x004711", "must not hold control characters"),
        ("order\x7f4711", "must not hold control characters"),
    ],
)
def test_invalid_keys_are_refused(
    key: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_idempotency_key(key)

    with pytest.raises(ValidationError, match=message):
        idempotency(key=key)


def test_the_key_limit_counts_characters_not_bytes() -> None:
    key = "ü" * MAX_IDEMPOTENCY_KEY_LENGTH

    assert len(key.encode("utf-8")) > MAX_IDEMPOTENCY_KEY_LENGTH
    assert validate_idempotency_key(key) == key


@pytest.mark.parametrize(
    "request_digest",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        " " + "a" * 63,
    ],
)
def test_request_digest_must_be_lowercase_hex_sha256(
    request_digest: str,
) -> None:
    with pytest.raises(ValidationError):
        idempotency(request_digest=request_digest)


def test_idempotency_shape_is_closed() -> None:
    with pytest.raises(ValidationError):
        InvocationIdempotency.model_validate(
            {
                "key": KEY,
                "request_digest": DIGEST,
                "expires_at": "2026-12-31T00:00:00Z",
            }
        )


def test_idempotency_is_immutable() -> None:
    record = idempotency()

    with pytest.raises(ValidationError, match="Instance is frozen"):
        record.__setattr__("key", "other")


# Invocations


def test_invocation_defaults_to_no_idempotency() -> None:
    invocation = ProductionInvocation(
        workflow_id=WORKFLOW_ID,
        initial_context=Context(),
    )

    assert invocation.idempotency is None


def test_invocation_payload_from_before_adr_0097_still_loads() -> None:
    invocation = ProductionInvocation(
        id=INVOCATION_ID,
        workflow_id=WORKFLOW_ID,
        initial_context=Context(),
    )

    legacy = invocation.model_dump(mode="json")
    del legacy["idempotency"]

    assert ProductionInvocation.model_validate(legacy) == invocation


def test_invocation_round_trips_its_idempotency() -> None:
    invocation = ProductionInvocation(
        id=INVOCATION_ID,
        workflow_id=WORKFLOW_ID,
        initial_context=Context(),
        idempotency=idempotency(),
    )

    restored = ProductionInvocation.model_validate_json(invocation.model_dump_json())

    assert restored == invocation
    assert restored.idempotency == idempotency()


def test_create_production_invocation_records_idempotency() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"request": "hello"},
        idempotency=idempotency(),
    )

    assert invocation.idempotency == idempotency()


def test_create_production_invocation_records_no_idempotency_by_default() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"request": "hello"},
    )

    assert invocation.idempotency is None


def test_idempotency_does_not_enter_the_invocation_context() -> None:
    with_key = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"request": "hello"},
        idempotency=idempotency(),
    )

    without_key = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"request": "hello"},
    )

    assert [(event.event_type, event.payload) for event in with_key.initial_context.events] == [
        (event.event_type, event.payload) for event in without_key.initial_context.events
    ]


# Invoking


def test_invoking_records_the_key_on_the_saved_invocation() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload={"request": "hello"},
            production_state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
            idempotency=idempotency(),
        )
    )

    assert isinstance(result, ProductionInvocationSuccess)

    invocation = invocation_repository.invocation_for_idempotency_key(KEY)

    assert invocation is not None
    assert invocation.id == result.invocation_id
    assert invocation.idempotency == idempotency()
    assert invocation_repository.result(invocation.id) == result


def test_an_undeployed_workflow_still_records_the_key() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=UNDEPLOYED_WORKFLOW_ID,
            payload="hello",
            production_state=None,
            catalog=create_catalog(),
            registry=create_registry(),
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
            idempotency=idempotency(),
        )
    )

    assert isinstance(result, ProductionInvocationFailure)
    assert result.error_code is ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED

    invocation = invocation_repository.invocation_for_idempotency_key(KEY)

    assert invocation is not None
    assert invocation.id == result.invocation_id
    assert invocation_repository.result(invocation.id) == result


def test_invoking_under_a_used_key_saves_and_runs_nothing() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()
    run_repository = InMemoryWorkflowRunRepository()

    earlier = ProductionInvocation(
        id=INVOCATION_ID,
        workflow_id=WORKFLOW_ID,
        initial_context=Context(),
        idempotency=idempotency(request_digest=OTHER_DIGEST),
    )

    invocation_repository.save(earlier)

    with pytest.raises(IdempotencyKeyInUseError) as raised:
        asyncio.run(
            invoke_production_workflow(
                workflow_id=WORKFLOW_ID,
                payload={"request": "hello"},
                production_state=create_state(),
                catalog=create_catalog(),
                registry=create_registry(),
                invocation_repository=invocation_repository,
                run_repository=run_repository,
                invocation_run_repository=InMemoryProductionInvocationRunRepository(),
                idempotency=idempotency(),
            )
        )

    assert raised.value.key == KEY
    assert invocation_repository.invocations() == (earlier,)
    assert invocation_repository.invocation_for_idempotency_key(KEY) == earlier
    assert invocation_repository.result(INVOCATION_ID) is None
    assert run_repository.runs() == ()


def test_invoking_without_a_key_records_none() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload="hello",
            production_state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
        )
    )

    assert invocation_repository.invocations()[0].idempotency is None


def test_invoking_the_active_state_passes_the_key_through() -> None:
    runtime = AzathothRuntime(
        workflows=WorkflowCatalog(),
        production_states=(create_state(),),
        models=create_catalog(),
        portfolio=ModelPortfolio(),
        language_models=create_registry(),
    )

    invocation_repository = InMemoryProductionInvocationRepository()

    result = asyncio.run(
        invoke_active_production_workflow(
            runtime=runtime,
            workflow_id=WORKFLOW_ID,
            payload={"request": "hello"},
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
            idempotency=idempotency(),
        )
    )

    assert isinstance(result, ProductionInvocationSuccess)

    invocation = invocation_repository.invocation_for_idempotency_key(KEY)

    assert invocation is not None
    assert invocation.id == result.invocation_id
