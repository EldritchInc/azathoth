"""Experiment command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from azathoth.cli.parsing import (
    EXPERIMENT_ACTION_ATTRIBUTE,
    EXPERIMENT_ID_ATTRIBUTE,
    EXPERIMENT_SHOW_ACTION,
)

ExperimentIdentifierHandler = Callable[[UUID], int]


def dispatch_experiment_command(
    arguments: Namespace,
    *,
    show_experiment: ExperimentIdentifierHandler,
) -> int | None:
    """Dispatch one parsed experiment command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            EXPERIMENT_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == EXPERIMENT_SHOW_ACTION:
        return show_experiment(
            cast(
                UUID,
                getattr(
                    arguments,
                    EXPERIMENT_ID_ATTRIBUTE,
                ),
            )
        )

    return None
