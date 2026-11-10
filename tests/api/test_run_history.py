"""Contract tests for reading back the runs an instance kept (ADR 0121)."""

import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from azathoth import api
from azathoth.context import Context
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import DeterministicLanguageModel, LanguageModelRegistry
from azathoth.workflows import (
    JournalRunResumed,
    JournalRunStarted,
    RunJournalEntry,
    WorkflowMetadata,
)
from tests.api.test_check import (
    ALPHA,
    ANSWER_STEP_ID,
    WORKFLOW_ID,
    StaticDirectory,
    answer_step,
    document,
    fixed_to,
    identifier,
)
from tests.api.test_invoke import promote
from tests.api.test_runs import (
    COUNT_STEP_ID,
    COUNT_WORKFLOW_ID,
    FAIL_IMPLEMENTATION_ID,
    FAIL_STEP_ID,
    FAIL_WORKFLOW_ID,
    MISSING_ID,
    stock,
    tool_step,
    workflow,
)

REMOVED_WORKFLOW_ID = UUID("e0000000-0000-4000-8000-000000000002")

FAILURE_MESSAGE = f"Tool implementation {FAIL_IMPLEMENTATION_ID} failed during execution."


def count(
    instance: api.Azathoth,
    text: str,
) -> api.RunResult:
    """Run the word count workflow on some text, and wait for the clock to move on."""

    result = instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload=text))

    time.sleep(0.002)

    return result


#
# Listing runs
#


def test_a_workflows_runs_are_listed_newest_first(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    first = count(instance, "one")
    second = count(instance, "one two")

    listed = instance.runs.list(COUNT_WORKFLOW_ID)

    assert [summary.run_id for summary in listed] == [second.run_id, first.run_id]
    assert listed[0] == api.RunSummary(
        run_id=second.run_id,
        workflow_id=COUNT_WORKFLOW_ID,
        workflow_name=f"workflow {COUNT_WORKFLOW_ID}",
        workflow_revision=1,
        invocation_id=None,
        succeeded=True,
        error=None,
        sensitivity=api.Sensitivity.INTERNAL,
        started_at=second.started_at,
        completed_at=second.completed_at,
        command=f"azathoth run show {second.run_id}",
    )


def test_a_list_holds_only_its_workflows_runs(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    count(instance, "one")
    instance.runs.run(FAIL_WORKFLOW_ID, input=api.RunInput(payload="x"))

    [failed] = instance.runs.list(FAIL_WORKFLOW_ID)

    assert failed.workflow_id == FAIL_WORKFLOW_ID
    assert not failed.succeeded
    assert failed.error == api.RunError(
        code="workflow_execution_failed",
        step_id=FAIL_STEP_ID,
        exception_type="ToolExecutionError",
        message=FAILURE_MESSAGE,
    )


def test_a_list_is_limited_to_the_newest(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    count(instance, "one")
    newest = count(instance, "one two")

    assert [summary.run_id for summary in instance.runs.list(COUNT_WORKFLOW_ID, limit=1)] == [
        newest.run_id
    ]


def test_a_limit_below_one_is_refused(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    with pytest.raises(api.InvalidArgumentError) as raised:
        instance.runs.list(COUNT_WORKFLOW_ID, limit=0)

    assert str(raised.value) == api.LIMIT_MESSAGE


def test_a_workflow_that_never_ran_has_no_runs(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    assert instance.runs.list(COUNT_WORKFLOW_ID) == ()


def test_a_workflow_neither_configured_nor_run_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        instance.runs.list(MISSING_ID)

    assert str(raised.value) == f"Workflow {MISSING_ID} is not configured."


def test_a_run_is_judged_by_the_revision_it_ran(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    ran = count(instance, "one two")

    step = tool_step(COUNT_STEP_ID, "word_count")
    step["outputs"] = [{"name": "words", "path": ["count"]}]
    renamed = workflow(COUNT_WORKFLOW_ID, step)
    renamed["result"] = {"name": "words"}
    instance.workflows.import_document(renamed)

    again = count(instance, "one two three")

    detail = instance.runs.get(ran.run_id)

    assert detail.workflow_revision == 1
    assert detail.succeeded
    assert detail.result == 2

    renamed_run = instance.runs.get(again.run_id)

    assert renamed_run.workflow_revision == 2
    assert renamed_run.succeeded
    assert renamed_run.result == 3


def test_a_run_recorded_before_revisions_is_judged_by_the_latest(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)

    ran = count(instance, "one two")
    repositories = open_repositories(location)
    kept = repositories.runs.get(ran.run_id)

    assert kept is not None

    unrevisioned = kept.model_copy(update={"id": uuid4(), "workflow_revision": None})
    repositories.runs.save(unrevisioned)

    step = tool_step(COUNT_STEP_ID, "word_count")
    step["outputs"] = [{"name": "words", "path": ["count"]}]
    renamed = workflow(COUNT_WORKFLOW_ID, step)
    renamed["result"] = {"name": "words"}
    instance.workflows.import_document(renamed)

    detail = instance.runs.get(unrevisioned.id)

    assert detail.workflow_revision is None
    assert not detail.succeeded
    assert not detail.has_result
    assert detail.error is not None
    assert detail.error.code == "result_not_produced"


def test_a_run_of_a_workflow_no_longer_configured_failed_only_if_it_halted(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)

    repositories = open_repositories(location)
    removed = WorkflowMetadata(
        id=REMOVED_WORKFLOW_ID,
        name="removed",
        description="A workflow since removed.",
        version="1.0.0",
    )

    for result in (
        count(instance, "one two"),
        instance.runs.run(FAIL_WORKFLOW_ID, input=api.RunInput(payload="x")),
    ):
        kept = repositories.runs.get(result.run_id)

        assert kept is not None

        repositories.runs.save(kept.model_copy(update={"id": uuid4(), "workflow": removed}))

    failed, succeeded = instance.runs.list(REMOVED_WORKFLOW_ID)

    assert succeeded.succeeded
    assert succeeded.error is None
    assert not failed.succeeded
    assert failed.error is not None
    assert failed.error.step_id == FAIL_STEP_ID

    detail = instance.runs.get(succeeded.run_id)

    assert not detail.has_result
    assert detail.result is None


def test_a_production_run_names_its_invocation(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)
    promote(location, COUNT_WORKFLOW_ID)

    outcome = instance.runs.invoke(COUNT_WORKFLOW_ID, input="one two")

    [summary] = instance.runs.list(COUNT_WORKFLOW_ID)

    assert summary.invocation_id == outcome.invocation_id

    detail = instance.runs.get(summary.run_id)

    assert detail.invocation_id == outcome.invocation_id
    assert detail.has_input
    assert detail.input == "one two"
    assert detail.result == 2


#
# Reading one run
#


def test_a_run_is_read_back_with_its_input_result_and_steps(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    ran = count(instance, "one two three")

    detail = instance.runs.get(ran.run_id)

    assert detail.run_id == ran.run_id
    assert detail.workflow_id == COUNT_WORKFLOW_ID
    assert detail.succeeded
    assert detail.has_result
    assert detail.result == 3
    assert detail.has_input
    assert detail.input == "one two three"
    assert detail.resumes == 0
    assert detail.command == f"azathoth run show {ran.run_id}"

    [step] = detail.steps

    assert step.step_id == COUNT_STEP_ID
    assert step.status == "executed"
    assert step.layer == 0
    assert step.attempts == 1
    assert step.strategy == "word_count"
    assert step.output == {"count": 3}
    assert step.values == {"count": 3}
    assert step.failures == ()
    assert step.started_at is not None
    assert step.completed_at is not None
    assert ran.started_at <= step.started_at <= step.completed_at <= ran.completed_at


def test_a_run_given_no_input_says_so(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    ran = instance.runs.run(COUNT_WORKFLOW_ID)

    detail = instance.runs.get(ran.run_id)

    assert not detail.has_input
    assert detail.input is None


def test_a_null_input_is_input(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    ran = instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload=None))

    detail = instance.runs.get(ran.run_id)

    assert detail.has_input
    assert detail.input is None


def test_a_failed_step_names_every_failed_attempt(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)
    retried = tool_step(FAIL_STEP_ID, "explode")
    retried["retry_policy"] = {"max_attempts": 2, "initial_delay_seconds": 0.0}
    instance.workflows.import_document(workflow(FAIL_WORKFLOW_ID, retried))

    ran = instance.runs.run(FAIL_WORKFLOW_ID, input=api.RunInput(payload="x"))

    detail = instance.runs.get(ran.run_id)

    assert not detail.succeeded
    assert not detail.has_result
    assert detail.error == ran.error

    [step] = detail.steps

    assert step.status == "failed"
    assert step.attempts == 2
    assert step.strategy is None
    assert step.metrics is None
    assert step.output is None
    assert step.values == {}
    assert step.failures == (
        api.StepFailure(attempt=1, exception_type="ToolExecutionError", message=FAILURE_MESSAGE),
        api.StepFailure(attempt=2, exception_type="ToolExecutionError", message=FAILURE_MESSAGE),
    )

    kept = open_repositories(location).runs.get(ran.run_id)

    assert kept is not None

    first, second = kept.steps[0].attempts

    assert step.started_at == first.started_at
    assert step.completed_at == second.completed_at


def test_a_skipped_step_has_no_attempt(
    instance: api.Azathoth,
) -> None:
    stock(instance)
    first = tool_step(FAIL_STEP_ID, "word_count")
    unmet = tool_step(COUNT_STEP_ID, "word_count")
    unmet["depends_on"] = [str(FAIL_STEP_ID)]
    unmet["conditions"] = [
        {"source": {"producer_step_id": str(FAIL_STEP_ID), "name": "count"}, "expected": 99}
    ]
    document_ = workflow(FAIL_WORKFLOW_ID, first)
    document_["steps"] = [first, unmet]
    instance.workflows.import_document(document_)

    ran = instance.runs.run(FAIL_WORKFLOW_ID, input=api.RunInput(payload="x"))

    steps = instance.runs.get(ran.run_id).steps

    assert [(step.step_id, step.status) for step in steps] == [
        (FAIL_STEP_ID, "executed"),
        (COUNT_STEP_ID, "skipped"),
    ]

    skipped = steps[1]

    assert skipped.attempts == 0
    assert skipped.layer == 1
    assert skipped.started_at is None
    assert skipped.completed_at is None
    assert skipped.failures == ()
    assert skipped.values == {}


def test_a_prompt_step_names_its_model_and_what_it_measured(
    location: str,
) -> None:
    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory((ALPHA,)),),
        language_models=LanguageModelRegistry(
            {
                identifier(ALPHA): DeterministicLanguageModel(
                    provider=ALPHA.provider,
                    model=ALPHA.model,
                    response_text="An answer.",
                )
            }
        ),
    ) as instance:
        instance.workflows.import_document(document(answer_step(fixed_to(identifier(ALPHA)))))

        ran = instance.runs.run(WORKFLOW_ID)

        [step] = instance.runs.get(ran.run_id).steps

    assert step.step_id == ANSWER_STEP_ID
    assert step.output == "An answer."
    assert step.values == {"answer": "An answer."}
    assert step.metrics is not None
    assert step.metrics.provider == ALPHA.provider
    assert step.metrics.model == ALPHA.model


def test_a_resumed_run_says_how_often(
    instance: api.Azathoth,
    location: str,
) -> None:
    stock(instance)

    ran = count(instance, "one")
    journal = open_repositories(location).run_journal
    entries = journal.entries(ran.run_id)
    journal.append(
        RunJournalEntry(
            run_id=ran.run_id,
            position=len(entries) + 1,
            workflow_id=COUNT_WORKFLOW_ID,
            recorded_at=datetime.now(UTC),
            event=JournalRunResumed(resumed_at=datetime.now(UTC)),
        )
    )

    assert instance.runs.get(ran.run_id).resumes == 1


def test_a_run_that_has_not_finished_says_so(
    instance: api.Azathoth,
    location: str,
) -> None:
    run_id = UUID("e0000000-0000-4000-8000-000000000001")
    open_repositories(location).run_journal.append(
        RunJournalEntry(
            run_id=run_id,
            position=1,
            workflow_id=COUNT_WORKFLOW_ID,
            recorded_at=datetime.now(UTC),
            event=JournalRunStarted(
                workflow=WorkflowMetadata(
                    id=COUNT_WORKFLOW_ID,
                    name="count",
                    description="Count.",
                    version="1.0.0",
                ),
                initial_context=Context(),
                started_at=datetime.now(UTC),
            ),
        )
    )

    with pytest.raises(api.NotFoundError) as raised:
        instance.runs.get(run_id)

    assert str(raised.value) == (
        f"Run {run_id} has not finished; resume it with azathoth run resume {run_id}."
    )


def test_an_unknown_run_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        instance.runs.get(MISSING_ID)

    assert str(raised.value) == f"Run {MISSING_ID} was not found."


def test_a_run_is_its_own_json(
    instance: api.Azathoth,
) -> None:
    stock(instance)

    detail = instance.runs.get(count(instance, "one").run_id)

    assert api.RunDetail.model_validate_json(detail.model_dump_json()) == detail


def test_a_closed_instance_reads_no_run(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.runs.list(COUNT_WORKFLOW_ID)

    with pytest.raises(api.InstanceClosedError):
        opened.runs.get(MISSING_ID)
