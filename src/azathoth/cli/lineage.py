"""Reading the lineage a child `azathoth` was started with (ADR 0104)."""

import os
from collections.abc import Mapping
from uuid import UUID

from azathoth.context import (
    LineageError,
    WorkflowLineage,
    child_lineage,
    decode_step_lineage,
)
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE


def parent_lineage(
    workflow_id: UUID,
    environ: Mapping[str, str] | None = None,
) -> WorkflowLineage | None:
    """Return the lineage a run of one workflow records, or `None` for a root run.

    A process tool's step hands its lineage to the `azathoth` it starts in
    `AZATHOTH_LINEAGE`. Without it, or with it empty, the run is a root. The
    run is one level below the step that started it, and is refused before
    anything is recorded when that is too deep.

    Raises:
        LineageError: `AZATHOTH_LINEAGE` is not a step's lineage.
        WorkflowDepthError: The run would be nested too deeply.
    """

    source = os.environ if environ is None else environ
    value = source.get(LINEAGE_ENVIRONMENT_VARIABLE, "")

    if not value:
        return None

    try:
        step = decode_step_lineage(value)
    except LineageError as error:
        raise LineageError(
            f"{LINEAGE_ENVIRONMENT_VARIABLE} is not valid lineage: {error}."
        ) from error

    return child_lineage(step, workflow_id=workflow_id)


__all__ = [
    "parent_lineage",
]
