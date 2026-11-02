"""Tests of the refusals `run resume` makes before anything executes (ADR 0105)."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from azathoth.cli.resumption import ConfiguredRunResumeError, resume_configured_workflow
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    InMemoryWorkflowRepository,
    WorkflowCatalog,
    WorkflowRunner,
)
from tests.workflows.test_run_resume import Counted, Crash, CrashingJournal
from tests.workflows.test_runner_journal import (
    FIRST_STEP_ID,
    INITIAL_CONTEXT,
    INVOCATION_ID,
    WORKFLOW_ID,
    candidate,
    step,
)


def interrupted_entries(
    *,
    revision: int | None = 3,
    invocation: bool = False,
) -> tuple[CrashingJournal, UUID]:
    """Return a journal with one interrupted run, and that run's ID."""

    journal = CrashingJournal()
    journal.crash("attempt.finished")

    with pytest.raises(Crash):
        asyncio.run(
            WorkflowRunner(journal=journal).run_recording_failures(
                replace(candidate(step(FIRST_STEP_ID, Counted("first"))), revision=revision),
                INITIAL_CONTEXT,
                invocation_id=INVOCATION_ID if invocation else None,
            )
        )

    (run_id,) = journal.run_ids

    return journal, run_id


RUNTIME = cast(RuntimeEnvironment, SimpleNamespace(workflows=WorkflowCatalog()))
"""A runtime that configures no workflow; the refusals come before it is used further."""


def refusal(
    journal: CrashingJournal,
    run_id: UUID,
) -> str:
    """Return what resuming the run refuses with."""

    with pytest.raises(ConfiguredRunResumeError) as error:
        asyncio.run(
            resume_configured_workflow(
                runtime=RUNTIME,
                run_id=run_id,
                entries=journal.entries(run_id),
                specifications=InMemoryWorkflowRepository(),
                runner=WorkflowRunner(journal=journal),
            )
        )

    return str(error.value)


def test_a_run_of_an_invocation_is_resumed_through_its_invocation() -> None:
    journal, run_id = interrupted_entries(invocation=True)

    assert refusal(journal, run_id) == (
        f"Run {run_id} executes invocation {INVOCATION_ID}; resume it with "
        f"azathoth invocation resume {INVOCATION_ID}."
    )


def test_a_run_whose_revision_is_gone_cannot_be_resumed() -> None:
    journal, run_id = interrupted_entries(revision=3)

    assert refusal(journal, run_id) == (
        f"Workflow {WORKFLOW_ID} has no revision 3 to resume run {run_id} with."
    )


def test_a_run_from_before_revisions_needs_its_workflow_configured() -> None:
    journal, run_id = interrupted_entries(revision=None)

    assert refusal(journal, run_id) == f"Workflow {WORKFLOW_ID} is not configured."
