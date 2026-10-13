"""Production invocation command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from azathoth.cli.parsing import (
    INVOCATION_ACTION_ATTRIBUTE,
    INVOCATION_ID_ATTRIBUTE,
    INVOCATION_SHOW_ACTION,
)

InvocationIdentifierHandler = Callable[[UUID], int]


def dispatch_invocation_command(
    arguments: Namespace,
    *,
    show_invocation: InvocationIdentifierHandler,
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

    return None
