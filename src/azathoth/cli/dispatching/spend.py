"""Spend command dispatch for the Azathoth CLI (ADR 0132)."""

from argparse import Namespace
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from azathoth.cli.parsing import (
    SPEND_BY_ATTRIBUTE,
    SPEND_GROUP_ATTRIBUTE,
    SPEND_OUTPUT_ATTRIBUTE,
    SPEND_OUTPUT_FILE_ATTRIBUTE,
    SPEND_SINCE_ATTRIBUTE,
    SPEND_TIME_ZONE_ATTRIBUTE,
    SPEND_UNTIL_ATTRIBUTE,
    SPEND_WORKFLOW_ATTRIBUTE,
)


class SpendHandler(Protocol):
    """Print what an instance spent, returning the exit code."""

    def __call__(
        self,
        *,
        since: str | None,
        until: str | None,
        by: str,
        group: str,
        time_zone: str | None,
        workflow_id: UUID | None,
        output_format: str,
        output_file: Path | None,
    ) -> int: ...


def dispatch_spend_command(
    arguments: Namespace,
    *,
    report_spend: SpendHandler,
) -> int:
    """Dispatch the parsed spend command."""

    return report_spend(
        since=cast(str | None, getattr(arguments, SPEND_SINCE_ATTRIBUTE)),
        until=cast(str | None, getattr(arguments, SPEND_UNTIL_ATTRIBUTE)),
        by=cast(str, getattr(arguments, SPEND_BY_ATTRIBUTE)),
        group=cast(str, getattr(arguments, SPEND_GROUP_ATTRIBUTE)),
        time_zone=cast(str | None, getattr(arguments, SPEND_TIME_ZONE_ATTRIBUTE)),
        workflow_id=cast(UUID | None, getattr(arguments, SPEND_WORKFLOW_ATTRIBUTE)),
        output_format=cast(str, getattr(arguments, SPEND_OUTPUT_ATTRIBUTE)),
        output_file=cast(Path | None, getattr(arguments, SPEND_OUTPUT_FILE_ATTRIBUTE)),
    )
