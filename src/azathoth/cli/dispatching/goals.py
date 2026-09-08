"""Goal command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from azathoth.cli.parsing import (
    GOAL_ACTION_ATTRIBUTE,
    GOAL_DOCUMENT_ATTRIBUTE,
    GOAL_ID_ATTRIBUTE,
    GOAL_IMPORT_ACTION,
    GOAL_LIST_ACTION,
    GOAL_SHOW_ACTION,
)

GoalIdentifierHandler = Callable[[UUID], int]
GoalImportHandler = Callable[[Path], int]
GoalListHandler = Callable[[], int]


def dispatch_goal_command(
    arguments: Namespace,
    *,
    import_goal: GoalImportHandler,
    list_goals: GoalListHandler,
    show_goal: GoalIdentifierHandler,
) -> int | None:
    """Dispatch one parsed goal command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            GOAL_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == GOAL_IMPORT_ACTION:
        return import_goal(
            cast(
                Path,
                getattr(
                    arguments,
                    GOAL_DOCUMENT_ATTRIBUTE,
                ),
            )
        )

    if action == GOAL_LIST_ACTION:
        return list_goals()

    if action == GOAL_SHOW_ACTION:
        return show_goal(
            cast(
                UUID,
                getattr(
                    arguments,
                    GOAL_ID_ATTRIBUTE,
                ),
            )
        )

    return None
