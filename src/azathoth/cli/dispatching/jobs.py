"""Job envelope command dispatch for the Azathoth CLI (ADR 0097)."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast

from azathoth.cli.parsing import (
    JOB_ACTION_ATTRIBUTE,
    JOB_REQUEST_ATTRIBUTE,
    JOB_RUN_ACTION,
)

JobRequestHandler = Callable[[str], int]


def dispatch_job_command(
    arguments: Namespace,
    *,
    run_job_request: JobRequestHandler,
) -> int | None:
    """Dispatch one parsed job envelope command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            JOB_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == JOB_RUN_ACTION:
        return run_job_request(
            cast(
                str,
                getattr(
                    arguments,
                    JOB_REQUEST_ATTRIBUTE,
                ),
            )
        )

    return None
