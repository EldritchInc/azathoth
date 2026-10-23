"""Semantic judge command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast

from azathoth.cli.parsing import (
    JUDGE_ACTION_ATTRIBUTE,
    JUDGE_ADD_ACTION,
    JUDGE_IDENTIFIER_ATTRIBUTE,
    JUDGE_LIST_ACTION,
    JUDGE_REMOVE_ACTION,
)

JudgeIdentifierHandler = Callable[[str], int]
JudgeListHandler = Callable[[], int]


def dispatch_judge_command(
    arguments: Namespace,
    *,
    add_judge: JudgeIdentifierHandler,
    list_judges: JudgeListHandler,
    remove_judge: JudgeIdentifierHandler,
) -> int | None:
    """Dispatch one parsed semantic judge command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            JUDGE_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == JUDGE_ADD_ACTION:
        return add_judge(
            cast(
                str,
                getattr(
                    arguments,
                    JUDGE_IDENTIFIER_ATTRIBUTE,
                ),
            )
        )

    if action == JUDGE_LIST_ACTION:
        return list_judges()

    if action == JUDGE_REMOVE_ACTION:
        return remove_judge(
            cast(
                str,
                getattr(
                    arguments,
                    JUDGE_IDENTIFIER_ATTRIBUTE,
                ),
            )
        )

    return None
