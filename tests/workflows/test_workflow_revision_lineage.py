"""Tests for carrying workflow specification revisions through execution."""

import asyncio
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.cli import execute_configured_benchmark
from azathoth.context import Context
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.runtime import AzathothRuntime
from azathoth.workflows import (
    InMemoryWorkflowBenchmarkExecutionRepository,
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    InMemoryWorkflowRepository,
    InMemoryWorkflowRunEvaluationRepository,
    InMemoryWorkflowRunRepository,
    WorkflowBenchmarkEvidenceRecorder,
    WorkflowCandidate,
    WorkflowCandidateSignature,
    WorkflowCatalog,
    WorkflowCatalogLoader,
    WorkflowProductionState,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    create_workflow_input_event,
    generate_production_workflow_candidate,
    promote_workflow_candidate,
)
from tests.cli.test_benchmark_execution import (
    WORKFLOW_ID,
    create_dataset,
    create_implementation_catalog,
    create_tool_catalog,
    create_workflow,
)
from tests.model_authorization import portfolio_for_catalog

STRATEGY_ID = UUID("88888888-8888-4888-8888-888888888888")


def create_changed_workflow() -> WorkflowSpecification:
    """Create the word-count workflow with changed content."""

    workflow = create_workflow()

    return workflow.model_copy(
        update={
            "metadata": workflow.metadata.model_copy(
                update={
                    "description": "Count words, second revision.",
                },
            ),
        },
    )


def create_catalog() -> WorkflowCatalog:
    """Catalog the word-count workflow after two imports."""

    repository = InMemoryWorkflowRepository()

    repository.save(create_workflow())
    repository.save(create_changed_workflow())

    return WorkflowCatalogLoader(repository).load_catalog()


def create_runtime(
    catalog: WorkflowCatalog,
) -> AzathothRuntime:
    """Create an executable runtime over one workflow catalog."""

    models = ModelCatalog()

    return AzathothRuntime(
        workflows=catalog,
        models=models,
        portfolio=portfolio_for_catalog(models),
        language_models=LanguageModelRegistry(),
        tools=create_tool_catalog(),
        tool_implementations=create_implementation_catalog(),
    )


def run_candidate(
    candidate: WorkflowCandidate,
) -> WorkflowRun:
    """Execute one word-count candidate on fixed input."""

    return asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(
                events=(
                    create_workflow_input_event(
                        "one two three",
                        producer="test",
                    ),
                ),
            ),
        )
    )


def without_key(
    payload: str,
    key: str,
) -> str:
    """Return a JSON document with one top-level key removed."""

    document = json.loads(payload)

    del document[key]

    return json.dumps(document)


def test_signatures_default_to_no_revision() -> None:
    signature = WorkflowCandidateSignature(
        workflow_id=WORKFLOW_ID,
        strategy_ids=(STRATEGY_ID,),
    )

    assert signature.workflow_revision is None


def test_signatures_reject_revisions_below_one() -> None:
    with pytest.raises(ValidationError):
        WorkflowCandidateSignature(
            workflow_id=WORKFLOW_ID,
            workflow_revision=0,
            strategy_ids=(STRATEGY_ID,),
        )


def test_signatures_of_different_revisions_differ() -> None:
    first = WorkflowCandidateSignature(
        workflow_id=WORKFLOW_ID,
        workflow_revision=1,
        strategy_ids=(STRATEGY_ID,),
    )

    second = first.model_copy(
        update={
            "workflow_revision": 2,
        },
    )

    assert first != second


def test_signatures_written_before_revisions_decode_without_one() -> None:
    signature = WorkflowCandidateSignature(
        workflow_id=WORKFLOW_ID,
        workflow_revision=3,
        strategy_ids=(STRATEGY_ID,),
    )

    decoded = WorkflowCandidateSignature.model_validate_json(
        without_key(
            signature.model_dump_json(),
            "workflow_revision",
        )
    )

    assert decoded.workflow_revision is None


def test_candidates_reject_revisions_below_one() -> None:
    candidate = create_runtime(create_catalog()).generate_workflow_candidate(WORKFLOW_ID)

    with pytest.raises(
        ValueError,
        match="Workflow candidate revision must be at least 1.",
    ):
        WorkflowCandidate(
            metadata=candidate.metadata,
            steps=candidate.steps,
            result=candidate.result,
            revision=0,
        )


def test_catalog_revisions_must_reference_catalogued_workflows() -> None:
    with pytest.raises(
        ValidationError,
        match="Workflow catalog revisions must reference catalogued workflows.",
    ):
        WorkflowCatalog(
            specifications=(create_workflow(),),
            revisions={
                UUID(int=1): 1,
            },
        )


def test_catalog_revision_numbers_must_be_positive() -> None:
    with pytest.raises(
        ValidationError,
        match="Workflow catalog revision numbers must be at least 1.",
    ):
        WorkflowCatalog(
            specifications=(create_workflow(),),
            revisions={
                WORKFLOW_ID: 0,
            },
        )


def test_catalog_without_revisions_knows_none() -> None:
    catalog = WorkflowCatalog(
        specifications=(create_workflow(),),
    )

    assert catalog.revision_number(WORKFLOW_ID) is None


def test_runtime_generates_the_latest_revision() -> None:
    candidate = create_runtime(create_catalog()).generate_workflow_candidate(WORKFLOW_ID)

    assert candidate.metadata == create_changed_workflow().metadata
    assert candidate.revision == 2
    assert candidate.signature.workflow_revision == 2


def test_runtime_without_catalogued_revisions_generates_unrevisioned_candidates() -> None:
    runtime = create_runtime(
        WorkflowCatalog(
            specifications=(create_workflow(),),
        )
    )

    candidate = runtime.generate_workflow_candidate(WORKFLOW_ID)

    assert candidate.revision is None
    assert candidate.signature.workflow_revision is None


def test_runs_record_the_revision_they_executed() -> None:
    candidate = create_runtime(create_catalog()).generate_workflow_candidate(WORKFLOW_ID)

    assert run_candidate(candidate).workflow_revision == 2


def test_runs_of_unrevisioned_candidates_record_no_revision() -> None:
    candidate = create_runtime(
        WorkflowCatalog(
            specifications=(create_workflow(),),
        )
    ).generate_workflow_candidate(WORKFLOW_ID)

    assert run_candidate(candidate).workflow_revision is None


def test_runs_written_before_revisions_decode_without_one() -> None:
    candidate = create_runtime(create_catalog()).generate_workflow_candidate(WORKFLOW_ID)

    run = run_candidate(candidate)

    decoded = WorkflowRun.model_validate_json(
        without_key(
            run.model_dump_json(),
            "workflow_revision",
        )
    )

    assert decoded.workflow_revision is None
    assert decoded.id == run.id


def test_promotion_records_the_promoted_revision() -> None:
    runtime = create_runtime(create_catalog())

    candidate = runtime.generate_workflow_candidate(WORKFLOW_ID)

    revision = promote_workflow_candidate(
        specification=create_changed_workflow(),
        candidate=candidate,
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    assert revision.state.specification_revision == 2


def test_production_runs_record_the_promoted_revision() -> None:
    runtime = create_runtime(create_catalog())

    revision = promote_workflow_candidate(
        specification=create_changed_workflow(),
        candidate=runtime.generate_workflow_candidate(WORKFLOW_ID),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    production_candidate = generate_production_workflow_candidate(
        state=revision.state,
        catalog=runtime.models,
        registry=runtime.language_models,
        tool_resolver=runtime.tool_resolver,
        tool_implementation_resolver=runtime.tool_implementation_resolver,
    )

    assert production_candidate.revision == 2
    assert run_candidate(production_candidate).workflow_revision == 2


def test_production_states_written_before_revisions_decode_without_one() -> None:
    runtime = create_runtime(create_catalog())

    revision = promote_workflow_candidate(
        specification=create_changed_workflow(),
        candidate=runtime.generate_workflow_candidate(WORKFLOW_ID),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    decoded = WorkflowProductionState.model_validate_json(
        without_key(
            revision.state.model_dump_json(),
            "specification_revision",
        )
    )

    assert decoded.specification_revision is None


def test_benchmark_executions_record_the_revision_they_judged() -> None:
    recorder = WorkflowBenchmarkEvidenceRecorder(
        runs=InMemoryWorkflowRunRepository(),
        evaluations=InMemoryWorkflowRunEvaluationRepository(),
        executions=InMemoryWorkflowBenchmarkExecutionRepository(),
    )

    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(create_catalog()),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
            recorder=recorder,
        )
    )

    (execution,) = recorder.executions.executions()

    assert execution.candidates[0].candidate_signature.workflow_revision == 2
    assert {case.run.workflow_revision for case in result.cases} == {2}
