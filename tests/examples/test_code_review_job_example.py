"""Tests proving the code-review example's job request (ADR 0097)."""

import asyncio
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import JsonValue

from azathoth.inputs import (
    FILE_SCHEME,
    FileInputResolver,
    InlineInput,
    InMemoryContentStore,
    InputPolicy,
    InputProvenance,
)
from azathoth.jobs import (
    JobResult,
    JobStatus,
    parse_job_request,
    run_job_content,
)
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    InvocationIdempotency,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    create_production_invocation,
    decode_workflow_document,
)

REVIEW_EXAMPLES = Path(__file__).parents[2] / "examples" / "code-review"

JOB_DOCUMENT = REVIEW_EXAMPLES / "jobs" / "review-rename.json"

RENAME_CHANGE_DOCUMENT = REVIEW_EXAMPLES / "changes" / "rename.json"

REVIEW_WORKFLOW_DOCUMENT = REVIEW_EXAMPLES / "workflows" / "review-change.json"

README = REVIEW_EXAMPLES / "README.md"

REVIEW: JsonValue = {
    "verdict": "approve",
    "findings": [],
    "counts": {"high": 0, "medium": 0, "low": 0},
    "summary": "No issues found.",
}


class ReviewInvoker:
    """Record the invocation and answer with the review production would emit."""

    def __init__(
        self,
        repository: InMemoryProductionInvocationRepository,
    ) -> None:
        self.repository = repository
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
        self.calls.append({"workflow_id": workflow_id, "payload": payload})

        invocation = create_production_invocation(
            workflow_id=workflow_id,
            payload=payload,
            caller_metadata=caller_metadata,
            input_provenance=input_provenance,
            idempotency=idempotency,
        )

        self.repository.save(invocation)

        result = ProductionInvocationSuccess(
            invocation_id=invocation.id,
            result={"result": REVIEW},
        )

        self.repository.save_result(result)

        return result


def test_the_job_request_decodes() -> None:
    request = parse_job_request(JOB_DOCUMENT.read_bytes())

    assert request.kind == "invoke"
    assert request.version == 1
    assert request.idempotency_key == "code-review-rename-1"
    assert request.caller_metadata == {"source": "examples/code-review"}


def test_the_job_names_the_review_workflow() -> None:
    request = parse_job_request(JOB_DOCUMENT.read_bytes())

    workflow = decode_workflow_document(REVIEW_WORKFLOW_DOCUMENT.read_text(encoding="utf-8"))

    assert request.workflow_id == workflow.metadata.id


def test_the_job_carries_the_rename_change_inline() -> None:
    request = parse_job_request(JOB_DOCUMENT.read_bytes())

    assert request.input == InlineInput(
        value=json.loads(RENAME_CHANGE_DOCUMENT.read_text(encoding="utf-8")),
    )


def test_the_job_runs_once_and_then_replays() -> None:
    repository = InMemoryProductionInvocationRepository()
    invoker = ReviewInvoker(repository)

    def run() -> JobResult:
        return asyncio.run(
            run_job_content(
                JOB_DOCUMENT.read_bytes(),
                policy=InputPolicy(resolvers={FILE_SCHEME: FileInputResolver()}),
                store=InMemoryContentStore(),
                invocation_repository=repository,
                invoke=invoker,
            )
        )

    first = run()
    again = run()

    assert first.status is JobStatus.SUCCEEDED
    assert first.replayed is False
    assert first.result == {"result": REVIEW}
    assert again.replayed is True
    assert again.invocation_id == first.invocation_id
    assert invoker.calls == [
        {
            "workflow_id": UUID("d2000000-0000-4000-8000-000000000010"),
            "payload": json.loads(RENAME_CHANGE_DOCUMENT.read_text(encoding="utf-8")),
        }
    ]


def test_the_walkthrough_shows_the_jobs_result_envelope() -> None:
    section = README.read_text(encoding="utf-8").split("## As a Job\n", 1)[1]

    assert "azathoth job run examples/code-review/jobs/review-rename.json" in section

    matched = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)

    assert matched is not None

    result = JobResult.model_validate_json(
        matched.group(1).replace("<INVOCATION_ID>", "55555555-5555-5555-5555-555555555555")
    )

    assert result.status is JobStatus.SUCCEEDED
    assert result.idempotency_key == "code-review-rename-1"
    assert result.result == {"result": REVIEW}
