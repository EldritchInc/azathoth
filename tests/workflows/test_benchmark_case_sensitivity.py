"""Tests that cases take the labels of their sources, and evidence the dataset's (ADR 0123)."""

import asyncio
import json
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.cli import compare_configured_benchmarks, execute_configured_benchmark
from azathoth.context import (
    INPUT_SENSITIVITY_EVENT_TYPE,
    LineageRun,
    LineageStep,
    StepLineage,
    child_lineage,
    context_sensitivity,
    create_input_sensitivity_event,
    create_lineage_event,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.inputs import InputProvenance, ResolvedInput, content_bytes_digest
from azathoth.sensitivity import Sensitivity, stored_sensitivity
from azathoth.workflows import (
    BENCHMARK_INPUT_PRODUCER,
    WORKFLOW_INPUT_EVENT_TYPE,
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    BenchmarkCaseSourceError,
    InMemoryWorkflowExperimentRepository,
    InMemoryWorkflowRunEvaluationRepository,
    InMemoryWorkflowRunRepository,
    WorkflowBenchmarkExecutionRecord,
    WorkflowExperimentEvidenceRecorder,
    WorkflowExperimentRecord,
    WorkflowExperimentRunner,
    WorkflowRun,
    WorkflowScorer,
    benchmark_case_context,
    benchmark_case_from_input,
    benchmark_case_from_run,
)
from tests.cli.test_benchmark_comparison import (
    CORRECT_WORKFLOW_ID,
    INCORRECT_WORKFLOW_ID,
)
from tests.cli.test_benchmark_comparison import create_dataset as create_comparison_dataset
from tests.cli.test_benchmark_comparison import create_runtime as create_comparison_runtime
from tests.cli.test_benchmark_execution import WORKFLOW_ID, create_dataset
from tests.cli.test_benchmark_execution_rendering import create_run as create_execution
from tests.cli.test_experiment_rendering import create_experiment
from tests.workflows.test_benchmark_case_source import RUN_ID, create_run, input_event
from tests.workflows.test_benchmark_digest_lineage import POLICY, create_benchmark_recorder
from tests.workflows.test_workflow_revision_lineage import create_catalog, create_runtime

EXPECTED = ExpectedOutcome(description="Received.", value=1, comparison=OutcomeComparison.EXACT)

PDF = b"%PDF-1.7\n%%EOF\n"

PROVENANCE = InputProvenance(
    uri="file:///claims/0412.pdf",
    media_type="application/pdf",
    size_bytes=len(PDF),
    digest=content_bytes_digest(PDF),
)

HANDLE: JsonValue = {
    "content": {
        "digest": content_bytes_digest(PDF),
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
    }
}


def labelled_run(
    label: Sensitivity,
) -> WorkflowRun:
    return create_run(input_event(), create_input_sensitivity_event(label, producer="test"))


def restricted(
    dataset: BenchmarkDataset,
) -> BenchmarkDataset:
    """Return a dataset whose first case is restricted."""

    first, *rest = dataset.cases

    return dataset.model_copy(
        update={"cases": (first.model_copy(update={"sensitivity": Sensitivity.RESTRICTED}), *rest)}
    )


# A case's run


def test_an_unlabelled_cases_run_records_no_label() -> None:
    context = benchmark_case_context(BenchmarkCase(input=1, expected=EXPECTED))

    assert [event.event_type for event in context.events] == [WORKFLOW_INPUT_EVENT_TYPE]


@pytest.mark.parametrize("label", list(Sensitivity))
def test_a_labelled_cases_run_records_its_label_last(
    label: Sensitivity,
) -> None:
    received, labelled = benchmark_case_context(
        BenchmarkCase(input=1, expected=EXPECTED, sensitivity=label)
    ).events

    assert received.event_type == WORKFLOW_INPUT_EVENT_TYPE
    assert (labelled.event_type, labelled.payload, labelled.producer) == (
        INPUT_SENSITIVITY_EVENT_TYPE,
        {"sensitivity": label.value},
        BENCHMARK_INPUT_PRODUCER,
    )
    assert labelled.occurred_at == received.occurred_at


def test_a_labelled_case_with_provenance_records_both() -> None:
    context = benchmark_case_context(
        BenchmarkCase(
            input=HANDLE,
            input_provenance=PROVENANCE,
            expected=EXPECTED,
            sensitivity=Sensitivity.RESTRICTED,
        )
    )

    assert [event.event_type for event in context.events] == [
        WORKFLOW_INPUT_EVENT_TYPE,
        WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
        INPUT_SENSITIVITY_EVENT_TYPE,
    ]
    assert context.events[-1].producer == BENCHMARK_INPUT_PRODUCER
    assert context_sensitivity(context) is Sensitivity.RESTRICTED


# Cases from runs


@pytest.mark.parametrize("label", list(Sensitivity))
def test_a_case_from_a_run_takes_the_runs_label(
    label: Sensitivity,
) -> None:
    case = benchmark_case_from_run(
        labelled_run(label),
        comparison=OutcomeComparison.EXACT,
        expected=1,
    )

    assert case.sensitivity is stored_sensitivity(label)


def test_a_case_from_an_unlabelled_run_is_unlabelled() -> None:
    case = benchmark_case_from_run(
        create_run(input_event()),
        comparison=OutcomeComparison.EXACT,
        expected=1,
    )

    assert case.sensitivity is None
    assert "sensitivity" not in case.model_dump(mode="json")


def test_a_case_from_a_run_may_be_labelled_more_sensitive() -> None:
    case = benchmark_case_from_run(
        labelled_run(Sensitivity.PUBLIC),
        comparison=OutcomeComparison.EXACT,
        expected=1,
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert case.sensitivity is Sensitivity.RESTRICTED


def test_a_case_from_a_run_labelled_as_the_run_is_takes_that_label() -> None:
    case = benchmark_case_from_run(
        labelled_run(Sensitivity.PUBLIC),
        comparison=OutcomeComparison.EXACT,
        expected=1,
        sensitivity=Sensitivity.PUBLIC,
    )

    assert case.sensitivity is Sensitivity.PUBLIC


@pytest.mark.parametrize(
    ("run_label", "case_label"),
    [
        (Sensitivity.RESTRICTED, Sensitivity.INTERNAL),
        (Sensitivity.RESTRICTED, Sensitivity.PUBLIC),
        (Sensitivity.INTERNAL, Sensitivity.PUBLIC),
    ],
)
def test_a_case_from_a_run_is_never_less_sensitive_than_the_run(
    run_label: Sensitivity,
    case_label: Sensitivity,
) -> None:
    with pytest.raises(BenchmarkCaseSourceError) as caught:
        benchmark_case_from_run(
            labelled_run(run_label),
            comparison=OutcomeComparison.EXACT,
            expected=1,
            sensitivity=case_label,
        )

    assert str(caught.value) == (
        f"Run {RUN_ID} is {run_label.value}; a case made from it cannot be {case_label.value}."
    )


def test_a_case_from_a_child_of_a_restricted_run_is_restricted() -> None:
    parent = StepLineage(
        step=LineageStep(
            workflow_id=UUID(int=1),
            run_id=UUID(int=2),
            step_id=UUID(int=3),
            attempt=1,
        ),
        depth=0,
        root=LineageRun(workflow_id=UUID(int=1), run_id=UUID(int=2)),
        sensitivity=Sensitivity.RESTRICTED,
    )

    run = create_run(
        input_event(), create_lineage_event(child_lineage(parent, workflow_id=UUID(int=4)))
    )

    case = benchmark_case_from_run(run, comparison=OutcomeComparison.EXACT, expected=1)

    assert case.sensitivity is Sensitivity.RESTRICTED

    with pytest.raises(BenchmarkCaseSourceError):
        benchmark_case_from_run(
            run,
            comparison=OutcomeComparison.EXACT,
            expected=1,
            sensitivity=Sensitivity.INTERNAL,
        )


# Cases from inputs


@pytest.mark.parametrize(
    ("label", "stored"),
    [
        (None, None),
        (Sensitivity.PUBLIC, Sensitivity.PUBLIC),
        (Sensitivity.INTERNAL, None),
        (Sensitivity.RESTRICTED, Sensitivity.RESTRICTED),
    ],
)
def test_a_case_from_an_input_takes_its_label(
    label: Sensitivity | None,
    stored: Sensitivity | None,
) -> None:
    case = benchmark_case_from_input(
        ResolvedInput(value="Claim 412.", media_type="text/plain", sensitivity=label),
        comparison=OutcomeComparison.EXACT,
        expected=1,
    )

    assert case.sensitivity is stored


# Evidence


def test_a_benchmark_run_records_the_datasets_label() -> None:
    recorder = create_benchmark_recorder()

    result = asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(create_catalog()),
            workflow_id=WORKFLOW_ID,
            dataset=restricted(create_dataset()),
            recorder=recorder,
        )
    )

    (execution,) = recorder.executions.executions()

    assert result.dataset_sensitivity is Sensitivity.RESTRICTED
    assert execution.sensitivity is Sensitivity.RESTRICTED
    assert sorted(
        context_sensitivity(run.initial_context).value for run in recorder.runs.runs()
    ) == ["internal", "restricted"]


def test_an_internal_benchmark_run_records_no_label() -> None:
    recorder = create_benchmark_recorder()

    asyncio.run(
        execute_configured_benchmark(
            runtime=create_runtime(create_catalog()),
            workflow_id=WORKFLOW_ID,
            dataset=create_dataset(),
            recorder=recorder,
        )
    )

    (execution,) = recorder.executions.executions()

    assert execution.sensitivity is None
    assert "sensitivity" not in json.loads(execution.model_dump_json())


def test_a_benchmark_comparison_records_the_datasets_label() -> None:
    recorder = create_benchmark_recorder()

    asyncio.run(
        compare_configured_benchmarks(
            runtime=create_comparison_runtime(),
            workflow_ids=(CORRECT_WORKFLOW_ID, INCORRECT_WORKFLOW_ID),
            dataset=restricted(create_comparison_dataset()),
            scoring_policy=POLICY,
            recorder=recorder,
        )
    )

    (execution,) = recorder.executions.executions()

    assert execution.sensitivity is Sensitivity.RESTRICTED


@pytest.mark.parametrize(
    ("dataset", "label"),
    [
        (restricted(create_comparison_dataset()), Sensitivity.RESTRICTED),
        (create_comparison_dataset(), None),
    ],
    ids=["restricted", "internal"],
)
def test_an_experiment_records_the_datasets_label(
    dataset: BenchmarkDataset,
    label: Sensitivity | None,
) -> None:
    recorder = WorkflowExperimentEvidenceRecorder(
        runs=InMemoryWorkflowRunRepository(),
        evaluations=InMemoryWorkflowRunEvaluationRepository(),
        experiments=InMemoryWorkflowExperimentRepository(),
    )

    asyncio.run(
        WorkflowExperimentRunner(scorer=WorkflowScorer(policy=POLICY), recorder=recorder).run(
            workflows=(
                create_comparison_runtime().generate_workflow_candidate(CORRECT_WORKFLOW_ID),
            ),
            dataset=dataset,
        )
    )

    (experiment,) = recorder.experiments.experiments()

    assert experiment.sensitivity is label


def test_labelled_records_read_back_and_unlabelled_ones_dump_as_before() -> None:
    execution = create_execution()
    experiment = create_experiment()

    assert "sensitivity" not in json.loads(execution.model_dump_json())
    assert "sensitivity" not in json.loads(experiment.model_dump_json())

    labelled_execution = execution.model_copy(update={"sensitivity": Sensitivity.RESTRICTED})
    labelled_experiment = experiment.model_copy(update={"sensitivity": Sensitivity.PUBLIC})

    assert (
        WorkflowBenchmarkExecutionRecord.model_validate_json(labelled_execution.model_dump_json())
        == labelled_execution
    )
    assert (
        WorkflowExperimentRecord.model_validate_json(labelled_experiment.model_dump_json())
        == labelled_experiment
    )
