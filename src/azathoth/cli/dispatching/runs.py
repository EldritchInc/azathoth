"""Run command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.parsing import (
    RUN_ACTION_ATTRIBUTE,
    RUN_FEEDBACK_ACTION,
    RUN_FEEDBACK_CORRECTED_OUTPUT_ATTRIBUTE,
    RUN_FEEDBACK_DISPOSITION_ATTRIBUTE,
    RUN_FEEDBACK_REASON_ATTRIBUTE,
    RUN_ID_ATTRIBUTE,
    RUN_SHOW_ACTION,
)
from azathoth.workflows import WorkflowRunFeedbackDisposition

RunFeedbackHandler = Callable[..., int]
RunIdentifierHandler = Callable[[UUID], int]


def dispatch_run_command(
    arguments: Namespace,
    *,
    record_run_feedback: RunFeedbackHandler,
    show_run: RunIdentifierHandler,
) -> int | None:
    """Dispatch one parsed run command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            RUN_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == RUN_SHOW_ACTION:
        return show_run(
            cast(
                UUID,
                getattr(
                    arguments,
                    RUN_ID_ATTRIBUTE,
                ),
            )
        )

    if action == RUN_FEEDBACK_ACTION:
        return record_run_feedback(
            cast(
                UUID,
                getattr(
                    arguments,
                    RUN_ID_ATTRIBUTE,
                ),
            ),
            disposition=WorkflowRunFeedbackDisposition(
                cast(
                    str,
                    getattr(
                        arguments,
                        RUN_FEEDBACK_DISPOSITION_ATTRIBUTE,
                    ),
                )
            ),
            reason=cast(
                str | None,
                getattr(
                    arguments,
                    RUN_FEEDBACK_REASON_ATTRIBUTE,
                    None,
                ),
            ),
            corrected_output=cast(
                JsonValue,
                getattr(
                    arguments,
                    RUN_FEEDBACK_CORRECTED_OUTPUT_ATTRIBUTE,
                    None,
                ),
            ),
        )

    return None
