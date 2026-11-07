"""Production invocation command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.cli.parsing import (
    INVOCATION_ACTION_ATTRIBUTE,
    INVOCATION_ANNOTATIONS_ACTION,
    INVOCATION_ID_ATTRIBUTE,
    INVOCATION_OUTPUT_ATTRIBUTE,
    INVOCATION_RESUME_ACTION,
    INVOCATION_SHOW_ACTION,
)

InvocationIdentifierHandler = Callable[[UUID], int]
InvocationResumeHandler = Callable[..., int]


def dispatch_invocation_command(
    arguments: Namespace,
    *,
    show_invocation: InvocationIdentifierHandler,
    resume_invocation: InvocationResumeHandler,
    export_invocation_annotations: InvocationIdentifierHandler,
) -> int | None:
    """Dispatch one parsed production invocation command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            INVOCATION_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == INVOCATION_SHOW_ACTION:
        return show_invocation(
            cast(
                UUID,
                getattr(
                    arguments,
                    INVOCATION_ID_ATTRIBUTE,
                ),
            )
        )

    if action == INVOCATION_ANNOTATIONS_ACTION:
        return export_invocation_annotations(
            cast(UUID, getattr(arguments, INVOCATION_ID_ATTRIBUTE))
        )

    if action == INVOCATION_RESUME_ACTION:
        return resume_invocation(
            cast(UUID, getattr(arguments, INVOCATION_ID_ATTRIBUTE)),
            output=WorkflowOutputFormat(cast(str, getattr(arguments, INVOCATION_OUTPUT_ATTRIBUTE))),
        )

    return None
