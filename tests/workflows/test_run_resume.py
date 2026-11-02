"""Tests that an interrupted run resumes from its journal where it stopped (ADR 0105)."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    InMemoryRunLeaseRepository,
    JournalAttemptFinished,
    JournalLayerCommitted,
    JournalRunStarted,
    RunJournalEntry,
    RunLease,
    RunLeaseHeldError,
    RunResumeError,
    WorkflowCandidate,
    WorkflowFailurePolicy,
    WorkflowRun,
    WorkflowRunner,
    WorkflowStepStatus,
    finished_run,
    journal_resumes,
    resume_point,
)
from tests.workflows.test_runner_journal import (
    FIRST_STEP_ID,
    INITIAL_CONTEXT,
    INVOCATION_ID,
    LATER_STEP_ID,
    SECOND_STEP_ID,
    candidate,
    rebuilt,
    step,
)


class Crash(BaseException):
    """The process dying: nothing after it runs, and nothing catches it."""


class CrashingJournal(InMemoryRunJournalRepository):
    """Record entries until a given one, then die instead of recording it."""

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.crash_before: str | None = None
        self.crash_count = 1
        self.run_ids: set[UUID] = set()

    def crash(
        self,
        event_type: str,
        *,
        nth: int = 1,
    ) -> None:
        """Die before recording the nth entry of this type from now on."""

        self.crash_before = event_type
        self.crash_count = nth

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        if entry.event.type == self.crash_before:
            self.crash_count -= 1

            if self.crash_count == 0:
                self.crash_before = None
                raise Crash()

        super().append(entry)
        self.run_ids.add(entry.run_id)


class Counted:
    """A step that counts its executions, fails as told, and may block until released."""

    def __init__(
        self,
        name: str,
        *,
        failures: int = 0,
        always_fail: bool = False,
        hold: asyncio.Event | None = None,
    ) -> None:
        self._name = name
        self._failures = failures
        self._always_fail = always_fail
        self._hold = hold
        self.calls = 0

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return StrategyMetadata(
            id=UUID("c1700000-0000-4000-8000-000000000021"),
            name=f"Counted {self._name}",
            description="Count executions.",
            version="1.0.0",
        )

    async def run(self, context: Context) -> StrategyOutcome:
        """Count the call, then fail or succeed."""

        self.calls += 1

        if self._hold is not None:
            await self._hold.wait()

        if self._always_fail:
            raise RuntimeError(f"{self._name} always fails")

        if self._failures > 0:
            self._failures -= 1
            raise RuntimeError(f"{self._name} fails for now")

        return StrategyOutcome(output=f"{self._name} done after {self.calls}")


def interrupt(
    workflow: WorkflowCandidate,
    journal: CrashingJournal,
    *,
    leases: InMemoryRunLeaseRepository | None = None,
    invocation_id: UUID | None = None,
) -> UUID:
    """Run the workflow until the journal crashes; return the interrupted run's ID."""

    with pytest.raises(Crash):
        asyncio.run(
            WorkflowRunner(journal=journal, leases=leases).run_recording_failures(
                workflow,
                INITIAL_CONTEXT,
                invocation_id=invocation_id,
            )
        )

    (run_id,) = journal.run_ids

    return run_id


def resume(
    workflow: WorkflowCandidate,
    journal: InMemoryRunJournalRepository,
    run_id: UUID,
    *,
    leases: InMemoryRunLeaseRepository | None = None,
) -> WorkflowRun:
    """Resume the run with a fresh runner, as another process would."""

    return asyncio.run(
        WorkflowRunner(journal=journal, leases=leases).resume(workflow, run_id=run_id)
    )


def types(
    journal: InMemoryRunJournalRepository,
    run_id: UUID,
) -> list[str]:
    """Return the run's journal entry types, in order."""

    return [entry.event.type for entry in journal.entries(run_id)]


# Resuming


def test_a_run_resumes_after_its_last_committed_layer_without_repeating_it() -> None:
    first = Counted("first")
    later = Counted("later")
    workflow = candidate(
        step(FIRST_STEP_ID, first),
        step(LATER_STEP_ID, later, depends_on=(FIRST_STEP_ID,)),
    )
    journal = CrashingJournal()
    journal.crash("attempt.started", nth=2)

    run_id = interrupt(workflow, journal)

    assert types(journal, run_id) == [
        "run.started",
        "attempt.started",
        "attempt.finished",
        "layer.committed",
    ]

    started = journal.entries(run_id)[0].event
    run = resume(workflow, journal, run_id)

    assert (first.calls, later.calls) == (1, 1)
    assert run.id == run_id
    assert run.succeeded
    assert run.initial_context == INITIAL_CONTEXT
    assert isinstance(started, JournalRunStarted)
    assert run.started_at == started.started_at
    assert [step_run.step_id for step_run in run.steps] == [FIRST_STEP_ID, LATER_STEP_ID]
    assert types(journal, run_id)[4:] == [
        "run.resumed",
        "attempt.started",
        "attempt.finished",
        "layer.committed",
        "run.finished",
    ]
    assert rebuilt(journal.entries(run_id)) == run
    assert finished_run(journal.entries(run_id)) == run


def test_the_resumed_run_keeps_the_committed_layers_evidence_exactly() -> None:
    workflow = candidate(
        step(FIRST_STEP_ID, Counted("first")),
        step(LATER_STEP_ID, Counted("later"), depends_on=(FIRST_STEP_ID,)),
    )
    journal = CrashingJournal()
    journal.crash("attempt.started", nth=2)

    run_id = interrupt(workflow, journal)
    committed = journal.entries(run_id)[3].event

    assert isinstance(committed, JournalLayerCommitted)

    run = resume(workflow, journal, run_id)

    assert run.steps[0] == committed.steps[0]
    assert run.final_context.events[: len(INITIAL_CONTEXT.events) + len(committed.events)] == (
        *INITIAL_CONTEXT.events,
        *committed.events,
    )


def test_an_attempt_that_never_finished_runs_again_under_the_same_number() -> None:
    first = Counted("first")
    workflow = candidate(step(FIRST_STEP_ID, first))
    journal = CrashingJournal()
    journal.crash("attempt.finished")

    run_id = interrupt(workflow, journal)

    assert types(journal, run_id) == ["run.started", "attempt.started"]

    run = resume(workflow, journal, run_id)

    assert first.calls == 2
    assert [attempt.attempt_number for attempt in run.steps[0].attempts] == [1]
    assert run.succeeded


def test_a_step_with_failed_attempts_continues_from_its_next_attempt() -> None:
    first = Counted("first", failures=1)
    workflow = candidate(step(FIRST_STEP_ID, first, attempts=3))
    journal = CrashingJournal()
    journal.crash("attempt.started", nth=2)

    run_id = interrupt(workflow, journal)

    recorded = journal.entries(run_id)[2].event

    assert isinstance(recorded, JournalAttemptFinished)
    assert recorded.attempt.failure is not None

    run = resume(workflow, journal, run_id)

    attempts = run.steps[0].attempts

    assert first.calls == 2
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert attempts[0] == recorded.attempt
    assert attempts[1].execution is not None
    assert run.succeeded


def test_a_layer_reuses_the_steps_that_finished_and_reruns_the_one_in_flight() -> None:
    hold = asyncio.Event()
    finished = Counted("finished")
    in_flight = Counted("in flight", hold=hold)
    workflow = candidate(
        step(FIRST_STEP_ID, finished),
        step(SECOND_STEP_ID, in_flight),
    )
    journal = CrashingJournal()

    #
    # The first step finishes while the second waits; then the process dies
    # before the second can finish.
    #
    journal.crash("attempt.finished", nth=2)
    hold.set()

    run_id = interrupt(workflow, journal)

    entries = journal.entries(run_id)
    (reused,) = (
        entry.event for entry in entries if isinstance(entry.event, JournalAttemptFinished)
    )

    run = resume(workflow, journal, run_id)

    assert (finished.calls, in_flight.calls) == (1, 2)
    assert [step_run.step_id for step_run in run.steps] == [FIRST_STEP_ID, SECOND_STEP_ID]

    by_step = {step_run.step_id: step_run for step_run in run.steps}

    assert by_step[reused.step_id].attempts == (reused.attempt,)
    assert by_step[reused.step_id].execution == reused.attempt.execution
    assert run.succeeded
    assert rebuilt(journal.entries(run_id)) == run


def test_a_step_whose_recorded_attempts_all_failed_fails_again_without_running() -> None:
    hold = asyncio.Event()
    failing = Counted("failing", always_fail=True)
    other = Counted("other", hold=hold)
    workflow = candidate(
        step(FIRST_STEP_ID, failing, attempts=1),
        step(SECOND_STEP_ID, other),
    )
    journal = CrashingJournal()
    journal.crash("attempt.finished", nth=2)
    hold.set()

    run_id = interrupt(workflow, journal)

    run = resume(workflow, journal, run_id)
    by_step = {step_run.step_id: step_run for step_run in run.steps}

    assert failing.calls == 1
    assert by_step[FIRST_STEP_ID].status is WorkflowStepStatus.FAILED
    failure = by_step[FIRST_STEP_ID].attempts[0].failure

    assert failure is not None
    assert failure.message == "failing always fails"
    assert run.halted
    assert run.halting_step_id == FIRST_STEP_ID


def test_a_run_that_halted_before_it_finished_finishes_halted_without_running() -> None:
    later = Counted("later")
    workflow = candidate(
        step(FIRST_STEP_ID, Counted("first", always_fail=True)),
        step(LATER_STEP_ID, later, depends_on=(FIRST_STEP_ID,)),
    )
    journal = CrashingJournal()
    journal.crash("run.finished")

    run_id = interrupt(workflow, journal)

    run = resume(workflow, journal, run_id)

    assert later.calls == 0
    assert run.halted
    assert run.halting_step_id == FIRST_STEP_ID
    assert types(journal, run_id)[-2:] == ["run.resumed", "run.finished"]


def test_a_finished_run_is_returned_as_it_finished_and_nothing_runs() -> None:
    first = Counted("first")
    workflow = candidate(step(FIRST_STEP_ID, first))
    journal = CrashingJournal()

    original = asyncio.run(
        WorkflowRunner(journal=journal).run_recording_failures(workflow, INITIAL_CONTEXT)
    )
    entries = journal.entries(original.id)

    assert resume(workflow, journal, original.id) == original
    assert first.calls == 1
    assert journal.entries(original.id) == entries


def test_a_run_interrupted_twice_counts_both_resumes() -> None:
    workflow = candidate(
        step(FIRST_STEP_ID, Counted("first")),
        step(SECOND_STEP_ID, Counted("second"), depends_on=(FIRST_STEP_ID,)),
        step(LATER_STEP_ID, Counted("later"), depends_on=(SECOND_STEP_ID,)),
    )
    journal = CrashingJournal()
    journal.crash("attempt.started", nth=2)

    run_id = interrupt(workflow, journal)

    journal.crash("attempt.started", nth=2)

    with pytest.raises(Crash):
        resume(workflow, journal, run_id)

    assert journal_resumes(journal.entries(run_id)) == 1

    run = resume(workflow, journal, run_id)

    assert run.succeeded
    assert journal_resumes(journal.entries(run_id)) == 2
    assert [step_run.step_id for step_run in run.steps] == [
        FIRST_STEP_ID,
        SECOND_STEP_ID,
        LATER_STEP_ID,
    ]


def test_a_resumed_run_journals_under_its_invocation() -> None:
    workflow = candidate(step(FIRST_STEP_ID, Counted("first")))
    journal = CrashingJournal()
    journal.crash("attempt.finished")

    run_id = interrupt(workflow, journal, invocation_id=INVOCATION_ID)

    asyncio.run(
        WorkflowRunner(journal=journal).resume(
            workflow,
            run_id=run_id,
            invocation_id=INVOCATION_ID,
        )
    )

    assert {entry.invocation_id for entry in journal.entries(run_id)} == {INVOCATION_ID}
    assert journal.invocation_run_id(INVOCATION_ID) == run_id


# Leases


def test_a_run_another_process_still_holds_is_refused() -> None:
    workflow = candidate(step(FIRST_STEP_ID, Counted("first")))
    journal = CrashingJournal()
    leases = InMemoryRunLeaseRepository()
    journal.crash("attempt.finished")

    run_id = interrupt(workflow, journal)

    now = datetime.now(UTC)
    leases.acquire(run_id, holder="still-running", now=now, duration=timedelta(seconds=60))

    with pytest.raises(RunLeaseHeldError) as error:
        resume(workflow, journal, run_id, leases=leases)

    expires = (now + timedelta(seconds=60)).isoformat(timespec="seconds")

    assert str(error.value) == f"Run {run_id} is still running (its lease expires at {expires})."
    assert types(journal, run_id) == ["run.started", "attempt.started"]


def test_a_run_whose_process_died_is_taken_over_once_its_lease_lapses() -> None:
    first = Counted("first")
    workflow = candidate(step(FIRST_STEP_ID, first))
    journal = CrashingJournal()
    leases = InMemoryRunLeaseRepository()
    journal.crash("attempt.finished")

    run_id = interrupt(workflow, journal)

    long_ago = datetime.now(UTC) - timedelta(minutes=5)
    leases.acquire(run_id, holder="dead-process", now=long_ago, duration=timedelta(seconds=60))

    run = resume(workflow, journal, run_id, leases=leases)

    assert run.succeeded
    assert leases.get(run_id) is None


# Refusals


def test_a_runner_without_a_journal_cannot_resume() -> None:
    with pytest.raises(ValueError, match=r"^A runner resumes only the runs it journals\.$"):
        asyncio.run(
            WorkflowRunner().resume(
                candidate(step(FIRST_STEP_ID, Counted("first"))),
                run_id=UUID(int=1),
            )
        )


def interrupted_journal() -> tuple[CrashingJournal, UUID, WorkflowCandidate]:
    """Return a journal whose run stopped after its first layer, and the workflow."""

    workflow = candidate(
        step(FIRST_STEP_ID, Counted("first")),
        step(LATER_STEP_ID, Counted("later"), depends_on=(FIRST_STEP_ID,)),
    )
    journal = CrashingJournal()
    journal.crash("attempt.started", nth=2)

    return journal, interrupt(workflow, journal), workflow


def test_a_run_with_no_journal_cannot_be_resumed() -> None:
    run_id = UUID("c1700000-0000-4000-8000-000000000099")

    with pytest.raises(RunResumeError) as error:
        resume(candidate(step(FIRST_STEP_ID, Counted("first"))), CrashingJournal(), run_id)

    assert str(error.value) == f"Run {run_id} has no journal to resume."
    assert error.value.run_id == run_id


def test_a_run_cannot_be_resumed_with_another_workflow() -> None:
    journal, run_id, workflow = interrupted_journal()
    other = replace(workflow, metadata=workflow.metadata.model_copy(update={"id": UUID(int=7)}))

    with pytest.raises(RunResumeError) as error:
        resume(other, journal, run_id)

    assert str(error.value) == (
        f"Run {run_id} executes workflow {workflow.metadata.id}, not workflow {UUID(int=7)}."
    )


@pytest.mark.parametrize(
    ("revision", "shown"),
    [(4, "revision 4"), (None, "no revision")],
)
def test_a_run_cannot_be_resumed_from_another_revision(
    revision: int | None,
    shown: str,
) -> None:
    journal, run_id, workflow = interrupted_journal()

    with pytest.raises(RunResumeError) as error:
        resume(replace(workflow, revision=revision), journal, run_id)

    assert str(error.value) == (
        f"Run {run_id} started from revision 3 of workflow {workflow.metadata.id}, not {shown}."
    )


def test_a_run_cannot_be_resumed_with_a_workflow_whose_layers_differ() -> None:
    journal, run_id, workflow = interrupted_journal()
    reshaped = candidate(
        step(SECOND_STEP_ID, Counted("second")),
        step(LATER_STEP_ID, Counted("later"), depends_on=(SECOND_STEP_ID,)),
    )

    with pytest.raises(RunResumeError) as error:
        resume(reshaped, journal, run_id)

    assert str(error.value) == (
        f"Run {run_id}'s journal does not match workflow {workflow.metadata.id}: "
        f"step {FIRST_STEP_ID} is not in layer 0."
    )


def test_a_journal_with_a_gap_cannot_be_resumed() -> None:
    journal, run_id, workflow = interrupted_journal()
    entries = journal.entries(run_id)
    holed = InMemoryRunJournalRepository()

    for entry in (*entries[:1], *entries[2:]):
        holed.append(entry)

    with pytest.raises(RunResumeError) as error:
        resume(workflow, holed, run_id)

    assert str(error.value) == f"Run {run_id}'s journal is missing position 2."


def test_a_finished_run_has_no_resume_point() -> None:
    workflow = candidate(step(FIRST_STEP_ID, Counted("first")))
    journal = InMemoryRunJournalRepository()
    run = asyncio.run(WorkflowRunner(journal=journal).run(workflow, INITIAL_CONTEXT))

    with pytest.raises(RunResumeError) as error:
        resume_point(journal.entries(run.id), run_id=run.id, workflow=workflow)

    assert str(error.value) == f"Run {run.id} has already finished."


def test_a_run_cannot_be_resumed_for_another_invocation() -> None:
    journal, run_id, workflow = interrupted_journal()

    with pytest.raises(RunResumeError) as error:
        asyncio.run(
            WorkflowRunner(journal=journal).resume(
                workflow,
                run_id=run_id,
                invocation_id=INVOCATION_ID,
            )
        )

    assert str(error.value) == (
        f"Run {run_id} executes no invocation, not invocation {INVOCATION_ID}."
    )


def test_an_unfinished_journal_is_not_a_finished_run() -> None:
    journal, run_id, _ = interrupted_journal()

    assert finished_run(journal.entries(run_id)) is None
    assert finished_run(()) is None


def test_skip_dependents_blocking_survives_a_resume() -> None:
    later = Counted("later")
    workflow = candidate(
        step(
            FIRST_STEP_ID,
            Counted("first", always_fail=True),
            failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
        ),
        step(SECOND_STEP_ID, Counted("second"), depends_on=(FIRST_STEP_ID,)),
        step(LATER_STEP_ID, later, depends_on=(SECOND_STEP_ID,)),
    )
    journal = CrashingJournal()
    journal.crash("layer.committed", nth=2)

    run_id = interrupt(workflow, journal)

    run = resume(workflow, journal, run_id)

    assert later.calls == 0
    assert [step_run.status for step_run in run.steps] == [
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.SKIPPED,
        WorkflowStepStatus.SKIPPED,
    ]
    assert not run.halted


def test_a_run_cannot_be_resumed_when_a_committed_layer_now_holds_other_steps() -> None:
    journal, run_id, workflow = interrupted_journal()
    widened = candidate(
        step(FIRST_STEP_ID, Counted("first")),
        step(SECOND_STEP_ID, Counted("second")),
        step(LATER_STEP_ID, Counted("later"), depends_on=(FIRST_STEP_ID,)),
    )

    with pytest.raises(RunResumeError) as error:
        resume_point(journal.entries(run_id), run_id=run_id, workflow=widened)

    assert str(error.value) == (
        f"Run {run_id}'s journal does not match workflow {workflow.metadata.id}: "
        "layer 0 commits other steps."
    )


# Documentation

WORKFLOWS_README = Path(__file__).parents[2] / "src" / "azathoth" / "workflows" / "README.md"


def refusal(
    entries: tuple[RunJournalEntry, ...],
    run_id: UUID,
    workflow: WorkflowCandidate,
) -> str:
    """Return the refusal resuming these entries with this workflow raises."""

    with pytest.raises(RunResumeError) as error:
        resume_point(entries, run_id=run_id, workflow=workflow)

    return str(error.value)


def test_the_readme_quotes_the_real_refusals() -> None:
    journal, run_id, workflow = interrupted_journal()
    entries = journal.entries(run_id)
    finished = InMemoryRunJournalRepository()
    done = asyncio.run(WorkflowRunner(journal=finished).run(workflow, INITIAL_CONTEXT))
    other_id = UUID(int=7)

    with pytest.raises(RunResumeError) as invocation:
        asyncio.run(
            WorkflowRunner(journal=journal).resume(
                workflow,
                run_id=run_id,
                invocation_id=INVOCATION_ID,
            )
        )

    messages = {
        refusal((), run_id, workflow),
        refusal(finished.entries(done.id), done.id, workflow).replace(str(done.id), str(run_id)),
        refusal((entries[0], *entries[2:]), run_id, workflow),
        refusal(
            entries,
            run_id,
            replace(workflow, metadata=workflow.metadata.model_copy(update={"id": other_id})),
        ),
        refusal(entries, run_id, replace(workflow, revision=4)),
        refusal(
            entries,
            run_id,
            candidate(
                step(FIRST_STEP_ID, Counted("first")),
                step(SECOND_STEP_ID, Counted("second")),
                step(LATER_STEP_ID, Counted("later"), depends_on=(FIRST_STEP_ID,)),
            ),
        ).replace("layer 0 commits other steps", "<DETAIL>"),
        str(invocation.value),
    }

    text = WORKFLOWS_README.read_text(encoding="utf-8")

    for message in messages:
        documented = (
            message.replace(str(run_id), "<RUN_ID>")
            .replace(f"workflow {other_id}", "workflow <OTHER_WORKFLOW_ID>")
            .replace(str(workflow.metadata.id), "<WORKFLOW_ID>")
            .replace(str(INVOCATION_ID), "<INVOCATION_ID>")
            .replace("revision 3", "revision <REVISION>")
            .replace("revision 4", "revision <OTHER_REVISION>")
            .replace("position 2", "position <POSITION>")
        )

        assert f"\n{documented}\n" in text, documented


ADR = Path(__file__).parents[2] / "docs" / "adrs" / "0105-resume-interrupted-runs-from-a-journal.md"


def test_the_adr_names_every_journal_entry_in_order() -> None:
    text = ADR.read_text(encoding="utf-8")
    section = text[text.index("### The journal") : text.index("### Schema version 2")]
    documented = [line.split("`")[1] for line in section.splitlines() if line.startswith("| `")]

    assert documented == [
        "run.started",
        "attempt.started",
        "attempt.finished",
        "layer.committed",
        "run.resumed",
        "run.finished",
    ]


def test_the_adr_quotes_the_real_lease_refusal() -> None:
    lease = RunLease(
        run_id=UUID(int=1),
        holder="holder",
        acquired_at=datetime(2026, 11, 1, tzinfo=UTC),
        expires_at=datetime(2026, 11, 1, 0, 1, tzinfo=UTC),
    )
    documented = (
        str(RunLeaseHeldError(lease))
        .replace(str(UUID(int=1)), "<RUN_ID>")
        .replace("2026-11-01T00:01:00+00:00", "<TIME>")
    )

    assert f"```text\n{documented}\n```" in ADR.read_text(encoding="utf-8")
