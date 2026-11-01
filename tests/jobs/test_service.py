"""Tests for running job requests (ADR 0097)."""

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.inputs import (
    FILE_SCHEME,
    FileInputResolver,
    InMemoryContentStore,
    InputPolicy,
    InputProvenance,
    content_bytes_digest,
    file_uri,
)
from azathoth.jobs import (
    JobErrorCode,
    JobResult,
    JobStatus,
    decode_job_request,
    job_request_digest,
    recorded_job_result,
    run_invoke_job,
    run_job,
    run_job_content,
    runtime_job_invoker,
)
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
    IdempotencyKeyInUseError,
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    InvocationIdempotency,
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    create_production_invocation,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

COMPETING_INVOCATION_ID = UUID("55555555-5555-5555-5555-555555555555")

KEY = "order-4711-review"

OTHER_KEY = "order-4712-review"

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)

FILE_POLICY = InputPolicy(
    resolvers={FILE_SCHEME: FileInputResolver()},
)


def request_data(
    **changes: Any,
) -> dict[str, Any]:
    """Return one valid request document, with changes."""

    data: dict[str, Any] = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": KEY,
        "workflow_id": str(WORKFLOW_ID),
        "input": {"value": {"change": "rename"}},
        "caller_metadata": {"ticket": "OPS-12"},
    }

    data.update(changes)

    return data


def file_request_data(
    path: Path,
    **changes: Any,
) -> dict[str, Any]:
    """Return one valid request document whose input is one JSON file."""

    return request_data(
        input={"uri": file_uri(path), "media_type": "application/json"},
        **changes,
    )


def digest_of(
    data: dict[str, Any],
) -> str:
    """Return the request digest of one request document."""

    return job_request_digest(decode_job_request(data))


class RecordingInvoker:
    """Record each invocation the way the production service does, and count calls.

    The invocation is saved with its idempotency before its result, so a key
    already in use raises before anything is recorded.
    """

    def __init__(
        self,
        repository: InMemoryProductionInvocationRepository,
        *,
        failure: ProductionInvocationErrorCode | None = None,
        result: JsonValue = None,
    ) -> None:
        self.repository = repository
        self.failure = failure
        self.result: JsonValue = {"verdict": "approve"} if result is None else result
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        workflow_id: UUID,
        payload: JsonValue,
        caller_metadata: Mapping[str, JsonValue],
        input_provenance: InputProvenance | None,
        idempotency: InvocationIdempotency,
    ) -> ProductionInvocationResult:
        self.calls.append(
            {
                "workflow_id": workflow_id,
                "payload": payload,
                "caller_metadata": dict(caller_metadata),
                "input_provenance": input_provenance,
                "idempotency": idempotency,
            }
        )

        invocation = create_production_invocation(
            workflow_id=workflow_id,
            payload=payload,
            caller_metadata=caller_metadata,
            input_provenance=input_provenance,
            idempotency=idempotency,
        )

        self.repository.save(invocation)

        result: ProductionInvocationResult

        if self.failure is None:
            result = ProductionInvocationSuccess(
                invocation_id=invocation.id,
                result=self.result,
            )
        else:
            result = ProductionInvocationFailure(
                invocation_id=invocation.id,
                error_code=self.failure,
                message="The invocation failed.",
            )

        self.repository.save_result(result)

        return result


class RacingInvoker:
    """Lose a race: another request records the key just before this one saves."""

    def __init__(
        self,
        repository: InMemoryProductionInvocationRepository,
        *,
        request_digest: str,
        with_result: bool,
    ) -> None:
        self.repository = repository
        self.request_digest = request_digest
        self.with_result = with_result
        self.calls = 0

    async def __call__(
        self,
        *,
        workflow_id: UUID,
        payload: JsonValue,
        caller_metadata: Mapping[str, JsonValue],
        input_provenance: InputProvenance | None,
        idempotency: InvocationIdempotency,
    ) -> ProductionInvocationResult:
        self.calls += 1

        self.repository.save(
            ProductionInvocation(
                id=COMPETING_INVOCATION_ID,
                workflow_id=workflow_id,
                initial_context=Context(),
                idempotency=InvocationIdempotency(
                    key=idempotency.key,
                    request_digest=self.request_digest,
                ),
            )
        )

        if self.with_result:
            self.repository.save_result(
                ProductionInvocationSuccess(
                    invocation_id=COMPETING_INVOCATION_ID,
                    result="the winner's result",
                )
            )

        raise IdempotencyKeyInUseError(idempotency.key)


class Harness:
    """One entry point's job dependencies, in memory."""

    def __init__(
        self,
        *,
        failure: ProductionInvocationErrorCode | None = None,
    ) -> None:
        self.repository = InMemoryProductionInvocationRepository()
        self.store = InMemoryContentStore()
        self.invoker = RecordingInvoker(self.repository, failure=failure)

    def run(
        self,
        data: JsonValue,
    ) -> JobResult:
        """Decode and run one job request."""

        return asyncio.run(
            run_job(
                data,
                policy=FILE_POLICY,
                store=self.store,
                invocation_repository=self.repository,
                invoke=self.invoker,
            )
        )

    def run_content(
        self,
        content: str | bytes,
    ) -> JobResult:
        """Parse and run one job request."""

        return asyncio.run(
            run_job_content(
                content,
                policy=FILE_POLICY,
                store=self.store,
                invocation_repository=self.repository,
                invoke=self.invoker,
            )
        )


# A first run


def test_a_first_run_invokes_and_succeeds() -> None:
    harness = Harness()

    result = harness.run(request_data())

    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is False
    assert result.idempotency_key == KEY
    assert result.result == {"verdict": "approve"}
    assert result.error is None

    invocation = harness.repository.invocation_for_idempotency_key(KEY)

    assert invocation is not None
    assert result.invocation_id == invocation.id


def test_a_first_run_passes_the_request_to_the_invoker() -> None:
    harness = Harness()

    harness.run(request_data())

    assert harness.invoker.calls == [
        {
            "workflow_id": WORKFLOW_ID,
            "payload": {"change": "rename"},
            "caller_metadata": {"ticket": "OPS-12"},
            "input_provenance": None,
            "idempotency": InvocationIdempotency(
                key=KEY,
                request_digest=digest_of(request_data()),
            ),
        }
    ]


def test_a_failed_invocation_is_a_failed_job_with_the_same_code() -> None:
    harness = Harness(failure=ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED)

    result = harness.run(request_data())

    assert result.status is JobStatus.FAILED
    assert result.replayed is False
    assert result.invocation_id is not None
    assert result.error is not None
    assert result.error.code is JobErrorCode.WORKFLOW_NOT_DEPLOYED


# Replays


def test_a_retry_replays_the_recorded_success_without_running() -> None:
    harness = Harness()

    first = harness.run(request_data())
    retry = harness.run(request_data())

    assert retry.status is JobStatus.SUCCEEDED
    assert retry.replayed is True
    assert retry.invocation_id == first.invocation_id
    assert retry.result == first.result
    assert len(harness.invoker.calls) == 1
    assert len(harness.repository.invocations()) == 1


def test_a_retry_replays_a_recorded_failure() -> None:
    harness = Harness(failure=ProductionInvocationErrorCode.MODEL_UNAVAILABLE)

    first = harness.run(request_data())
    retry = harness.run(request_data())

    assert retry.status is JobStatus.FAILED
    assert retry.replayed is True
    assert retry.invocation_id == first.invocation_id
    assert retry.error == first.error
    assert len(harness.invoker.calls) == 1


def test_a_retry_in_another_format_and_key_order_still_replays() -> None:
    harness = Harness()

    first = harness.run_content(json.dumps(request_data()))

    data = request_data()
    reordered = dict(reversed(list(data.items())))

    retry = harness.run_content(json.dumps(reordered, indent=2).encode("utf-8"))

    assert retry.replayed is True
    assert retry.invocation_id == first.invocation_id


def test_a_key_whose_invocation_has_no_result_is_incomplete() -> None:
    harness = Harness()

    interrupted = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"change": "rename"},
        idempotency=InvocationIdempotency(
            key=KEY,
            request_digest=digest_of(request_data()),
        ),
    )

    harness.repository.save(interrupted)

    result = harness.run(request_data())

    assert result.status is JobStatus.INCOMPLETE
    assert result.replayed is True
    assert result.invocation_id == interrupted.id
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVOCATION_INCOMPLETE
    assert harness.invoker.calls == []


def test_a_replay_needs_no_input_content(
    tmp_path: Path,
) -> None:
    harness = Harness()

    path = tmp_path / "change.json"
    path.write_text('{"change": "rename"}', encoding="utf-8")

    first = harness.run(file_request_data(path))

    path.unlink()

    retry = harness.run(file_request_data(path))

    assert retry.status is JobStatus.SUCCEEDED
    assert retry.replayed is True
    assert retry.invocation_id == first.invocation_id


def test_a_changed_file_under_the_same_key_replays_the_original_result(
    tmp_path: Path,
) -> None:
    harness = Harness()

    path = tmp_path / "change.json"
    path.write_text('{"change": "rename"}', encoding="utf-8")

    first = harness.run(file_request_data(path))

    path.write_text('{"change": "order-search"}', encoding="utf-8")

    retry = harness.run(file_request_data(path))

    assert retry.replayed is True
    assert retry.invocation_id == first.invocation_id
    assert len(harness.invoker.calls) == 1


# Conflicts


@pytest.mark.parametrize(
    "changes",
    [
        {"input": {"value": {"change": "order-search"}}},
        {"workflow_id": str(OTHER_WORKFLOW_ID)},
        {"caller_metadata": {"ticket": "OPS-13"}},
    ],
)
def test_a_used_key_with_a_different_request_is_a_conflict(
    changes: dict[str, Any],
) -> None:
    harness = Harness()

    harness.run(request_data())

    result = harness.run(request_data(**changes))

    assert result.status is JobStatus.REJECTED
    assert result.replayed is False
    assert result.invocation_id is None
    assert result.idempotency_key == KEY
    assert result.error is not None
    assert result.error.code is JobErrorCode.IDEMPOTENCY_CONFLICT
    assert repr(KEY) in result.error.message
    assert len(harness.invoker.calls) == 1


def test_a_conflict_is_reported_before_the_input_is_resolved(
    tmp_path: Path,
) -> None:
    harness = Harness()

    harness.run(request_data())

    result = harness.run(file_request_data(tmp_path / "missing.json"))

    assert result.error is not None
    assert result.error.code is JobErrorCode.IDEMPOTENCY_CONFLICT


def test_another_key_runs_the_same_request_again() -> None:
    harness = Harness()

    first = harness.run(request_data())
    again = harness.run(request_data(idempotency_key=OTHER_KEY))

    assert again.status is JobStatus.SUCCEEDED
    assert again.replayed is False
    assert again.invocation_id != first.invocation_id
    assert len(harness.invoker.calls) == 2


# Inputs


def test_an_inline_input_is_passed_as_its_value_without_provenance() -> None:
    harness = Harness()

    harness.run(request_data(input={"value": "Rename it.", "media_type": "text/plain"}))

    call = harness.invoker.calls[0]

    assert call["payload"] == "Rename it."
    assert call["input_provenance"] is None


def test_a_file_input_is_resolved_stored_and_passed_with_provenance(
    tmp_path: Path,
) -> None:
    harness = Harness()

    content = b'{"change": "rename"}'

    path = tmp_path / "change.json"
    path.write_bytes(content)

    result = harness.run(file_request_data(path))

    assert result.status is JobStatus.SUCCEEDED

    call = harness.invoker.calls[0]

    assert call["payload"] == {"change": "rename"}
    assert call["input_provenance"] == InputProvenance(
        uri=file_uri(path),
        media_type="application/json",
        size_bytes=len(content),
        digest=content_bytes_digest(content),
    )
    assert harness.store.get(content_bytes_digest(content)) == content


@pytest.mark.parametrize(
    "source",
    [
        {"uri": "s3://bucket/change.json", "media_type": "application/json"},
        {"uri": "https://example.com/change.json", "media_type": "application/json"},
    ],
)
def test_a_scheme_the_policy_refuses_is_rejected_as_invalid_input(
    source: dict[str, str],
) -> None:
    harness = Harness()

    result = harness.run(request_data(input=source))

    assert result.status is JobStatus.REJECTED
    assert result.invocation_id is None
    assert result.idempotency_key == KEY
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_INPUT
    assert "not accepted here" in result.error.message
    assert harness.invoker.calls == []
    assert harness.repository.invocations() == ()


def test_a_missing_file_is_rejected_as_invalid_input(
    tmp_path: Path,
) -> None:
    harness = Harness()

    result = harness.run(file_request_data(tmp_path / "missing.json"))

    assert result.status is JobStatus.REJECTED
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_INPUT
    assert harness.repository.invocations() == ()


def test_content_that_does_not_decode_is_rejected_and_not_stored(
    tmp_path: Path,
) -> None:
    harness = Harness()

    path = tmp_path / "change.json"
    path.write_text("{not json", encoding="utf-8")

    result = harness.run(file_request_data(path))

    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_INPUT
    assert not harness.store.contains(content_bytes_digest(b"{not json"))


def test_content_beyond_the_policy_cap_is_rejected(
    tmp_path: Path,
) -> None:
    repository = InMemoryProductionInvocationRepository()
    invoker = RecordingInvoker(repository)

    path = tmp_path / "change.json"
    path.write_text('{"change": "rename"}', encoding="utf-8")

    result = asyncio.run(
        run_job(
            file_request_data(path),
            policy=InputPolicy(
                resolvers={FILE_SCHEME: FileInputResolver()},
                max_bytes=4,
            ),
            store=InMemoryContentStore(),
            invocation_repository=repository,
            invoke=invoker,
        )
    )

    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_INPUT
    assert "larger than the limit" in result.error.message
    assert invoker.calls == []


def test_a_rejected_input_leaves_the_key_free(
    tmp_path: Path,
) -> None:
    harness = Harness()

    refused = harness.run(file_request_data(tmp_path / "missing.json"))

    assert refused.status is JobStatus.REJECTED

    fixed = harness.run(request_data())

    assert fixed.status is JobStatus.SUCCEEDED
    assert fixed.replayed is False


# Races


def race(
    *,
    request_digest: str,
    with_result: bool,
) -> tuple[JobResult, RacingInvoker]:
    """Run one request whose key another request records first."""

    repository = InMemoryProductionInvocationRepository()

    invoker = RacingInvoker(
        repository,
        request_digest=request_digest,
        with_result=with_result,
    )

    result = asyncio.run(
        run_job(
            request_data(),
            policy=FILE_POLICY,
            store=InMemoryContentStore(),
            invocation_repository=repository,
            invoke=invoker,
        )
    )

    return result, invoker


def test_losing_a_race_to_a_finished_invocation_replays_it() -> None:
    result, invoker = race(
        request_digest=digest_of(request_data()),
        with_result=True,
    )

    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is True
    assert result.invocation_id == COMPETING_INVOCATION_ID
    assert result.result == "the winner's result"
    assert invoker.calls == 1


def test_losing_a_race_to_a_running_invocation_is_incomplete() -> None:
    result, _ = race(
        request_digest=digest_of(request_data()),
        with_result=False,
    )

    assert result.status is JobStatus.INCOMPLETE
    assert result.invocation_id == COMPETING_INVOCATION_ID


def test_losing_a_race_to_a_different_request_is_a_conflict() -> None:
    result, _ = race(
        request_digest="f" * 64,
        with_result=True,
    )

    assert result.status is JobStatus.REJECTED
    assert result.error is not None
    assert result.error.code is JobErrorCode.IDEMPOTENCY_CONFLICT


def test_a_key_in_use_that_cannot_be_found_is_not_hidden() -> None:
    async def phantom(
        *,
        workflow_id: UUID,
        payload: JsonValue,
        caller_metadata: Mapping[str, JsonValue],
        input_provenance: InputProvenance | None,
        idempotency: InvocationIdempotency,
    ) -> ProductionInvocationResult:
        raise IdempotencyKeyInUseError(idempotency.key)

    with pytest.raises(IdempotencyKeyInUseError):
        asyncio.run(
            run_invoke_job(
                decode_job_request(request_data()),
                policy=FILE_POLICY,
                store=InMemoryContentStore(),
                invocation_repository=InMemoryProductionInvocationRepository(),
                invoke=phantom,
            )
        )


# Requests that do not decode


def test_a_request_that_does_not_decode_is_rejected_with_its_key() -> None:
    harness = Harness()

    data = request_data()
    del data["workflow_id"]

    result = harness.run(data)

    assert result.status is JobStatus.REJECTED
    assert result.idempotency_key == KEY
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_REQUEST
    assert harness.invoker.calls == []


def test_an_unsupported_version_is_rejected_by_name() -> None:
    result = Harness().run(request_data(version=2))

    assert result.status is JobStatus.REJECTED
    assert result.error is not None
    assert result.error.code is JobErrorCode.UNSUPPORTED_VERSION
    assert result.error.metadata == {"supported_versions": [1]}


def test_content_that_is_not_json_is_rejected_without_a_key() -> None:
    result = Harness().run_content("not json")

    assert result.status is JobStatus.REJECTED
    assert result.idempotency_key is None
    assert result.error is not None
    assert result.error.code is JobErrorCode.INVALID_REQUEST


def test_recorded_job_result_finds_nothing_for_an_unused_key() -> None:
    assert (
        recorded_job_result(
            KEY,
            request_digest=digest_of(request_data()),
            invocation_repository=InMemoryProductionInvocationRepository(),
        )
        is None
    )


# Invoking through a runtime


def create_state() -> WorkflowProductionState:
    """Create deterministic active production state."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="job-production",
                description="Exercise production invocation through a job.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="job-production-prompt",
                            description="Exercise production invocation through a job.",
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


def create_runtime() -> AzathothRuntime:
    """Create a runtime with one active production workflow."""

    return AzathothRuntime(
        workflows=WorkflowCatalog(),
        production_states=(create_state(),),
        models=ModelCatalog(
            models=(
                ModelMetadata(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                    display_name=PRIMARY.identifier,
                ),
            )
        ),
        portfolio=ModelPortfolio(),
        language_models=LanguageModelRegistry(
            {
                PRIMARY.identifier: DeterministicLanguageModel(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                ),
            }
        ),
    )


class RuntimeLoader:
    """Count how often the runtime is composed."""

    def __init__(
        self,
    ) -> None:
        self.loads = 0

    def __call__(
        self,
    ) -> AzathothRuntime:
        self.loads += 1

        return create_runtime()


class RuntimeHarness:
    """Run jobs through a runtime-bound invoker, in memory."""

    def __init__(
        self,
    ) -> None:
        self.loader = RuntimeLoader()
        self.repository = InMemoryProductionInvocationRepository()
        self.run_repository = InMemoryWorkflowRunRepository()
        self.invoke = runtime_job_invoker(
            self.loader,
            invocation_repository=self.repository,
            run_repository=self.run_repository,
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
        )

    def run(
        self,
        data: JsonValue,
    ) -> JobResult:
        """Decode and run one job request."""

        return asyncio.run(
            run_job(
                data,
                policy=FILE_POLICY,
                store=InMemoryContentStore(),
                invocation_repository=self.repository,
                invoke=self.invoke,
            )
        )


def test_a_runtime_invoker_runs_the_active_production_state() -> None:
    harness = RuntimeHarness()

    result = harness.run(request_data())

    assert result.status is JobStatus.SUCCEEDED
    assert harness.loader.loads == 1

    invocation = harness.repository.invocation_for_idempotency_key(KEY)

    assert invocation is not None
    assert invocation.id == result.invocation_id
    assert invocation.caller_metadata == {"ticket": "OPS-12"}
    assert invocation.idempotency == InvocationIdempotency(
        key=KEY,
        request_digest=digest_of(request_data()),
    )
    assert len(harness.run_repository.runs()) == 1


def test_a_runtime_invoker_reports_an_undeployed_workflow_as_a_failed_job() -> None:
    harness = RuntimeHarness()

    result = harness.run(request_data(workflow_id=str(OTHER_WORKFLOW_ID)))

    assert result.status is JobStatus.FAILED
    assert result.error is not None
    assert result.error.code is JobErrorCode.WORKFLOW_NOT_DEPLOYED

    retry = harness.run(request_data(workflow_id=str(OTHER_WORKFLOW_ID)))

    assert retry.status is JobStatus.FAILED
    assert retry.replayed is True


def test_a_runtime_is_composed_only_when_a_job_invokes() -> None:
    harness = RuntimeHarness()

    harness.run(request_data(version=2))
    harness.run(request_data(input={"uri": "s3://bucket/x.json", "media_type": "application/json"}))

    assert harness.loader.loads == 0

    harness.run(request_data())
    harness.run(request_data())
    harness.run(request_data(input={"value": "other"}))

    assert harness.loader.loads == 1


def test_a_runtime_invoker_is_composed_once_across_invocations() -> None:
    harness = RuntimeHarness()

    harness.run(request_data())
    harness.run(request_data(idempotency_key=OTHER_KEY))

    assert harness.loader.loads == 1
    assert len(harness.repository.invocations()) == 2
