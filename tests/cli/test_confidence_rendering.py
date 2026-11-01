"""Tests for showing step confidence in CLI output (ADR 0098)."""

import asyncio
import dataclasses
import io
import json
from pathlib import Path

import pytest

from azathoth.cli import render_workflow_run, show_workflow
from azathoth.cli.rendering import step_finished_record
from azathoth.cli.step_output import JsonLinesOutputWriter
from azathoth.context import Context
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunRepository,
    WorkflowRun,
    WorkflowRunner,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValueBinding,
)
from tests.cli.test_output_records import announced_step, finished
from tests.cli.test_rendering import successful_run
from tests.cli.test_workflow_import import (
    WORKFLOW_ID,
    configure_database,
    create_workflow,
)
from tests.workflows.test_step_confidence_execution import (
    CLASSIFY_STEP_ID,
    ScriptedExecutor,
    classifier_step,
    single_step_candidate,
)


def with_confidence(
    run: WorkflowRun,
    confidence: float | None,
) -> WorkflowRun:
    """Return the run with its one step recording a confidence."""

    return run.model_copy(
        update={
            "steps": (run.steps[0].model_copy(update={"confidence": confidence}),),
        }
    )


# run show and workflow run --output text


def test_a_step_run_names_its_confidence_after_its_strategy() -> None:
    rendered = render_workflow_run(with_confidence(successful_run(), 0.62))

    assert "Strategy: rendered strategy\nConfidence: 0.62\nProvider: openrouter\n" in rendered


@pytest.mark.parametrize(("confidence", "shown"), [(0.0, "0.0"), (1.0, "1.0")])
def test_the_bounds_render_as_numbers(
    confidence: float,
    shown: str,
) -> None:
    rendered = render_workflow_run(with_confidence(successful_run(), confidence))

    assert f"Confidence: {shown}\n" in rendered


def test_a_step_run_without_a_confidence_names_none() -> None:
    assert "Confidence" not in render_workflow_run(successful_run())


def test_a_recorded_confidence_survives_the_run_repository(
    tmp_path: Path,
) -> None:
    run = with_confidence(successful_run(), 0.62)

    repository = SQLiteWorkflowRunRepository(tmp_path / "azathoth.db")

    repository.save(run)

    restored = repository.get(run.id)

    assert restored is not None
    assert restored.steps[0].confidence == 0.62
    assert "Confidence: 0.62\n" in render_workflow_run(restored)


# JSON Lines output records


def test_an_output_record_carries_the_confidence_beside_the_values() -> None:
    event = dataclasses.replace(
        finished(announced_step(), WorkflowStepStatus.EXECUTED),
        confidence=0.62,
    )

    record = step_finished_record(event)

    assert record is not None
    assert record["values"] == {"count": 7}
    assert record["confidence"] == 0.62
    assert list(record) == ["type", "step_id", "values", "confidence"]


def test_an_output_record_without_a_confidence_omits_it() -> None:
    record = step_finished_record(finished(announced_step(), WorkflowStepStatus.EXECUTED))

    assert record is not None
    assert "confidence" not in record


def test_a_step_that_emits_no_values_emits_no_confidence() -> None:
    event = dataclasses.replace(
        finished(announced_step(emit_values=False), WorkflowStepStatus.EXECUTED),
        confidence=0.62,
    )

    assert step_finished_record(event) is None


def test_a_run_streams_the_confidence_of_a_step_that_emits_its_values() -> None:
    stream = io.StringIO()

    step = dataclasses.replace(
        classifier_step(),
        message="Classifying",
        emit_values=True,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=ScriptedExecutor(
                {"Classify": [{"category": "billing", "confidence": 0.62}]},
            ),
            observer=JsonLinesOutputWriter(stream),
        ).run_recording_failures(
            workflow=single_step_candidate(step),
            context=Context(),
        )
    )

    records = [json.loads(line) for line in stream.getvalue().splitlines()]

    assert records == [
        {"type": "step", "step_id": str(CLASSIFY_STEP_ID), "message": "Classifying"},
        {
            "type": "output",
            "step_id": str(CLASSIFY_STEP_ID),
            "values": {"category": "billing", "confidence": 0.62},
            "confidence": 0.62,
        },
    ]
    assert run.steps[0].confidence == 0.62


# workflow show


def show_stored_workflow(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    confidence: str | None,
) -> str:
    """Store the import test workflow, its step declaring a confidence or not, and show it."""

    database = tmp_path / "azathoth.db"

    workflow = create_workflow()

    step = WorkflowStepSpecification.model_validate(
        {
            **workflow.steps[0].model_dump(),
            "outputs": (
                WorkflowValueBinding(name="answer", path=("answer",)),
                WorkflowValueBinding(name="certainty", path=("certainty",)),
            ),
            "confidence": confidence,
        }
    )

    SQLiteWorkflowRepository(database).save(
        workflow.model_copy(update={"steps": (step,)}),
    )

    configure_database(database=database, monkeypatch=monkeypatch)

    assert show_workflow(WORKFLOW_ID) == 0

    captured = capsys.readouterr()

    assert captured.err == ""

    return captured.out


def test_workflow_show_names_a_steps_confidence_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = show_stored_workflow(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        confidence="certainty",
    )

    assert "Strategy: import prompt\nConfidence Output: certainty\nDependencies: 0\n" in output


def test_workflow_show_omits_confidence_for_a_step_without_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = show_stored_workflow(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        confidence=None,
    )

    assert "Confidence" not in output
