"""Human-readable kept runs, as the service API returns them (ADR 0140).

`run show` and `workflow runs` read the service API, so they show a run
the same whether it is kept on this machine or on a remote `--remote`
names. Each line is the one the command printed before it read the API.
"""

import json
from collections.abc import Sequence

from pydantic import JsonValue

from azathoth import api
from azathoth.cli.rendering._json import render_json_value
from azathoth.cli.rendering.resumes import render_child_count_lines, render_resume_lines
from azathoth.cli.rendering.run_summaries import UNJUDGED_RUN_DISPOSITION
from azathoth.cli.rendering.sensitivity import render_sensitivity_lines

HALTED_CODE = "workflow_execution_failed"
"""The code of the error of a run that halted on a failed step, which is a run that failed."""


def run_halted(
    run: api.RunSummary,
) -> bool:
    """Return whether a run halted on a failed step, as a run that failed did.

    A run that finished without producing its declared result did not halt,
    so its status is succeeded, as it always was.
    """

    return run.error is not None and run.error.code == HALTED_CODE


def _status(
    run: api.RunSummary,
) -> str:
    return "failed" if run_halted(run) else "succeeded"


def _duration(
    run: api.RunSummary,
) -> float:
    return (run.completed_at - run.started_at).total_seconds()


def _revision(
    number: int | None,
) -> str:
    return str(number) if number is not None else "unknown"


def render_run_summaries(
    runs: Sequence[api.RunSummary],
) -> str:
    """Render one line per run in the order given.

    Each line contains the run ID, start time, status, duration, what made
    it, and its latest judgment, or "-" for a run never judged.
    """

    return "\n".join(
        f"{run.run_id}  {run.started_at.isoformat()}  {_status(run):<9}  "
        f"{_duration(run):.3f}s  {run.source}  "
        f"{run.feedback if run.feedback is not None else UNJUDGED_RUN_DISPOSITION}"
        for run in runs
    )


def render_run_detail(
    run: api.RunDetail,
    *,
    children: int = 0,
) -> str:
    """Render one kept run for a human operator.

    A run a step of another run started names its depth, the parent step
    and the root run, right after its ID (ADR 0104). A run that was resumed
    names how often, after its lineage, and one whose steps started
    children names how many (ADR 0105). A run whose label is not internal
    names it right after its ID (ADR 0123).
    """

    steps = run.steps

    lines = [
        f"Workflow: {run.workflow_name}",
        f"Workflow ID: {run.workflow_id}",
        f"Workflow Revision: {_revision(run.workflow_revision)}",
        f"Run ID: {run.run_id}",
        *render_sensitivity_lines(run.sensitivity),
        *_lineage_lines(run.lineage),
        *render_resume_lines(run.resumes),
        *render_child_count_lines(children),
        f"Status: {_status(run)}",
        f"Duration: {_duration(run):.3f}s",
        f"Steps: {len(steps)}",
        f"Executed: {sum(step.status == 'executed' for step in steps)}",
        f"Failed: {sum(step.status == 'failed' for step in steps)}",
        f"Skipped: {sum(step.status == 'skipped' for step in steps)}",
        f"Retries: {sum(max(step.attempts - 1, 0) for step in steps)}",
    ]

    for index, step in enumerate(steps, start=1):
        lines.extend(
            (
                "",
                f"Step {index}",
                f"ID: {step.step_id}",
                f"Status: {step.status}",
                f"Attempts: {step.attempts}",
            )
        )

        if step.status == "executed":
            _append_execution(lines, step)
        elif step.status == "failed" and step.failures:
            failure = step.failures[-1]
            lines.append(f"Error: {failure.exception_type}: {failure.message}")

    return "\n".join(lines)


def _lineage_lines(
    lineage: api.RunLineage | None,
) -> list[str]:
    """Return the lines naming where a run came from, or none for a root run."""

    if lineage is None:
        return []

    return [
        f"Depth: {lineage.depth}",
        f"Parent Workflow ID: {lineage.parent_workflow_id}",
        f"Parent Run ID: {lineage.parent_run_id}",
        f"Parent Step ID: {lineage.parent_step_id} (attempt {lineage.parent_attempt})",
        f"Root Workflow ID: {lineage.root_workflow_id}",
        f"Root Run ID: {lineage.root_run_id}",
    ]


def _append_execution(
    lines: list[str],
    step: api.RunStepDetail,
) -> None:
    """Append what an executed step's strategy did and returned.

    A step that recorded a confidence names it after its strategy (ADR 0098).
    """

    lines.append(f"Strategy: {step.strategy}")

    if step.confidence is not None:
        lines.append(f"Confidence: {step.confidence}")

    metrics = step.metrics

    if metrics is not None:
        if metrics.provider is not None:
            lines.append(f"Provider: {metrics.provider}")

        if metrics.model is not None:
            lines.append(f"Model: {metrics.model}")

        if metrics.prompt_tokens is not None:
            lines.append(f"Prompt Tokens: {metrics.prompt_tokens}")

        if metrics.completion_tokens is not None:
            lines.append(f"Completion Tokens: {metrics.completion_tokens}")

        if metrics.total_tokens is not None:
            lines.append(f"Total Tokens: {metrics.total_tokens}")

        if metrics.latency_ms is not None:
            lines.append(f"Latency: {metrics.latency_ms} ms")

        if metrics.estimated_cost_usd is not None:
            lines.append(f"Estimated Cost: ${metrics.estimated_cost_usd:.6f}")

    lines.extend(f"Resource: {_render_resource(resource)}" for resource in step.resources)
    lines.extend(("Output:", render_json_value(step.output)))


def _render_resource(
    resource: api.StepResource,
) -> str:
    """Render one resource with its attributes in name order."""

    rendered = f"{resource.kind} {resource.identifier}"

    if not resource.attributes:
        return rendered

    attributes = ", ".join(
        f"{name}={_render_attribute(resource.attributes[name])}"
        for name in sorted(resource.attributes)
    )

    return f"{rendered} ({attributes})"


def _render_attribute(
    value: JsonValue,
) -> str:
    """Render one resource attribute compactly."""

    if isinstance(value, str):
        return value

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def render_run_evaluations(
    evaluations: Sequence[api.RunEvaluation],
) -> str:
    """Render every evaluator judgment of one run, in the order given."""

    if not evaluations:
        return "Evaluations: none"

    lines = [f"Evaluations: {len(evaluations)}"]

    for index, evaluation in enumerate(evaluations, start=1):
        lines.extend(
            (
                "",
                f"Evaluation {index}",
                f"ID: {evaluation.evaluation_id}",
                f"Evaluated: {evaluation.evaluated_at.isoformat()}",
                f"Evaluator: {evaluation.evaluator_name} {evaluation.evaluator_version}",
                f"Status: {evaluation.status}",
                f"Score: {evaluation.score:.6f} (threshold {evaluation.threshold:.6f})",
                f"Reason: {evaluation.reason}",
            )
        )
        lines.extend(
            f"Evidence: {item.label} = {json.dumps(item.value, ensure_ascii=False)}"
            for item in evaluation.evidence
        )

    return "\n".join(lines)


def render_run_feedback(
    feedback: Sequence[api.RunFeedback],
) -> str:
    """Render every judgment of one run, in the order given."""

    if not feedback:
        return "Feedback: none"

    lines = [f"Feedback: {len(feedback)}"]

    for index, record in enumerate(feedback, start=1):
        lines.extend(
            (
                "",
                f"Feedback {index}",
                f"ID: {record.feedback_id}",
                f"Created: {record.created_at.isoformat()}",
                f"Disposition: {record.disposition}",
            )
        )

        if record.reason is not None:
            lines.append(f"Reason: {record.reason}")

        if record.corrected_output is not None:
            lines.extend(("Corrected Output:", render_json_value(record.corrected_output)))

    return "\n".join(lines)


__all__ = [
    "HALTED_CODE",
    "render_run_detail",
    "render_run_evaluations",
    "render_run_feedback",
    "render_run_summaries",
    "run_halted",
]
