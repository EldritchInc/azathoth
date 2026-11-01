"""Job result envelope rendering (ADR 0097)."""

import json

from azathoth.jobs import JobResult


def render_job_result(
    result: JobResult,
) -> str:
    """Render one job result envelope as one line of JSON.

    Every field is present, `null` included, in the envelope's field order.
    """

    return json.dumps(
        result.model_dump(
            mode="json",
        ),
        ensure_ascii=False,
    )
