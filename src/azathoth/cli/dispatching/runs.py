"""Run command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from azathoth.cli.parsing import (
    RUN_ACTION_ATTRIBUTE,
    RUN_ID_ATTRIBUTE,
    RUN_SHOW_ACTION,
)

RunIdentifierHandler = Callable[[UUID], int]


def dispatch_run_command(
    arguments: Namespace,
    *,
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

    return None
