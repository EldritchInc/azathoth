"""Tests of the run journal's entries and the writer that numbers them (ADR 0105)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_args
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from azathoth.context import Context, ContextEvent
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    JournalAttemptFinished,
    JournalAttemptStarted,
    JournalLayerCommitted,
    JournalRunFinished,
    JournalRunStarted,
    RunJournalEntry,
    RunJournalEvent,
    RunJournalPositionTakenError,
    RunJournalWriter,
    WorkflowMetadata,
    WorkflowStepAttempt,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepStatus,
)

RUN_ID = UUID("c1200000-0000-4000-8000-000000000001")
OTHER_RUN_ID = UUID("c1200000-0000-4000-8000-000000000002")
WORKFLOW_ID = UUID("c1200000-0000-4000-8000-000000000003")
STEP_ID = UUID("c1200000-0000-4000-8000-000000000004")
INVOCATION_ID = UUID("c1200000-0000-4000-8000-000000000005")

AT = datetime(2026, 11, 1, 21, 0, tzinfo=UTC)

METADATA = WorkflowMetadata(
    id=WORKFLOW_ID,
    name="Journaled workflow",
    description="Record what each run does.",
    version="1.0.0",
)

FAILED_ATTEMPT = WorkflowStepAttempt(
    attempt_number=1,
    started_at=AT,
    completed_at=AT + timedelta(seconds=1),
    failure=WorkflowStepFailure(exception_type="RuntimeError", message="temporary failure"),
)

EVENTS: tuple[RunJournalEvent, ...] = (
    JournalRunStarted(
        workflow=METADATA,
        workflow_revision=2,
        initial_context=Context(
            events=(
                ContextEvent(
                    event_type="workflow.input.received",
                    payload={"input": {"text": "ü"}},
                    producer="test",
                ),
            )
        ),
        started_at=AT,
    ),
    JournalAttemptStarted(step_id=STEP_ID, layer_index=0, attempt_number=1, started_at=AT),
    JournalAttemptFinished(step_id=STEP_ID, layer_index=0, attempt=FAILED_ATTEMPT),
    JournalLayerCommitted(
        layer_index=0,
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.FAILED,
                attempts=(FAILED_ATTEMPT,),
            ),
        ),
        blocked_step_ids=(STEP_ID,),
    ),
    JournalRunFinished(completed_at=AT, halted=True, halting_step_id=STEP_ID),
)


def entry(
    event: RunJournalEvent,
    *,
    position: int = 1,
    run_id: UUID = RUN_ID,
    invocation_id: UUID | None = None,
) -> RunJournalEntry:
    """Return one entry of a run's journal."""

    return RunJournalEntry(
        run_id=run_id,
        position=position,
        workflow_id=WORKFLOW_ID,
        invocation_id=invocation_id,
        recorded_at=AT,
        event=event,
    )


# Entries


@pytest.mark.parametrize("event", EVENTS, ids=[event.type for event in EVENTS])
def test_every_kind_of_entry_survives_json(
    event: RunJournalEvent,
) -> None:
    original = entry(event, invocation_id=INVOCATION_ID)

    assert RunJournalEntry.model_validate_json(original.model_dump_json()) == original


def test_the_entry_types_are_named_as_the_journal_records_them() -> None:
    assert [event.type for event in EVENTS] == [
        "run.started",
        "attempt.started",
        "attempt.finished",
        "layer.committed",
        "run.finished",
    ]


def test_an_event_is_read_by_its_type() -> None:
    adapter: TypeAdapter[RunJournalEvent] = TypeAdapter(RunJournalEvent)

    event = adapter.validate_python(
        {"type": "run.finished", "completed_at": AT.isoformat(), "halted": False}
    )

    assert event == JournalRunFinished(completed_at=AT, halted=False)


def test_an_unknown_event_type_is_rejected() -> None:
    adapter: TypeAdapter[RunJournalEvent] = TypeAdapter(RunJournalEvent)

    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "run.paused"})


def test_a_journal_is_numbered_from_one() -> None:
    with pytest.raises(ValidationError):
        entry(EVENTS[0], position=0)


def test_an_entry_rejects_fields_it_does_not_know() -> None:
    with pytest.raises(ValidationError):
        RunJournalEntry.model_validate(
            {**entry(EVENTS[0]).model_dump(mode="json"), "lease": "holder-1"}
        )


def test_entries_are_frozen() -> None:
    with pytest.raises(ValidationError):
        entry(EVENTS[0]).position = 2


# The writer


def test_the_writer_numbers_entries_in_order_and_names_the_run_on_each() -> None:
    repository = InMemoryRunJournalRepository()
    writer = RunJournalWriter(
        repository,
        run_id=RUN_ID,
        workflow_id=WORKFLOW_ID,
        invocation_id=INVOCATION_ID,
        clock=lambda: AT,
    )

    recorded = [writer.record(event) for event in EVENTS]

    assert repository.entries(RUN_ID) == tuple(recorded)
    assert recorded == [
        entry(event, position=position, invocation_id=INVOCATION_ID)
        for position, event in enumerate(EVENTS, start=1)
    ]
    assert writer.next_position == 6
    assert writer.run_id == RUN_ID


def test_the_writer_may_continue_a_journal_at_a_later_position() -> None:
    repository = InMemoryRunJournalRepository()
    writer = RunJournalWriter(
        repository,
        run_id=RUN_ID,
        workflow_id=WORKFLOW_ID,
        next_position=4,
    )

    assert writer.record(EVENTS[1]).position == 4


def test_the_writer_refuses_a_position_before_the_first() -> None:
    with pytest.raises(ValueError, match=r"^A run's journal is numbered from 1\.$"):
        RunJournalWriter(
            InMemoryRunJournalRepository(),
            run_id=RUN_ID,
            workflow_id=WORKFLOW_ID,
            next_position=0,
        )


def test_the_writer_stays_at_a_position_another_writer_took() -> None:
    repository = InMemoryRunJournalRepository()
    repository.append(entry(EVENTS[0], position=1))

    writer = RunJournalWriter(repository, run_id=RUN_ID, workflow_id=WORKFLOW_ID)

    with pytest.raises(RunJournalPositionTakenError) as error:
        writer.record(EVENTS[0])

    assert str(error.value) == f"Run {RUN_ID} already records journal position 1."
    assert (error.value.run_id, error.value.position) == (RUN_ID, 1)
    assert writer.next_position == 1
    assert repository.entries(RUN_ID) == (entry(EVENTS[0], position=1),)


def test_the_writer_stamps_each_entry_with_the_current_time_by_default() -> None:
    before = datetime.now(UTC)

    recorded = RunJournalWriter(
        InMemoryRunJournalRepository(),
        run_id=RUN_ID,
        workflow_id=WORKFLOW_ID,
    ).record(EVENTS[0])

    assert before <= recorded.recorded_at <= datetime.now(UTC)


# Documentation

WORKFLOWS_README = Path(__file__).parents[2] / "src" / "azathoth" / "workflows" / "README.md"


def test_the_readme_names_every_entry_type_in_order() -> None:
    text = WORKFLOWS_README.read_text(encoding="utf-8")
    section = text[text.index("### The Run Journal") :]
    section = section[: section.index("\n### ", 1)]
    documented = [line.split("`")[1] for line in section.splitlines() if line.startswith("| `")]
    (union, _) = get_args(RunJournalEvent)

    assert documented == [kind.model_fields["type"].default for kind in get_args(union)]
    assert documented == [
        "run.started",
        "attempt.started",
        "attempt.finished",
        "layer.committed",
        "run.resumed",
        "run.finished",
    ]


def test_the_readme_quotes_the_real_collision() -> None:
    message = str(RunJournalPositionTakenError(RUN_ID, 7))

    documented = message.replace(str(RUN_ID), "<RUN_ID>").replace("7", "<POSITION>")

    assert f"```text\n{documented}\n```" in WORKFLOWS_README.read_text(encoding="utf-8")
