"""What an instance spent, through the service API (ADR 0132).

Spend is a ledger of model calls, each counted once: every kept run's,
production's, and its judges'. A report groups it into periods in a time
zone, billed and estimated apart, and is the `read_spend` action (ADR
0127). `azathoth spend` prints it, and `spend_csv` writes it for a
spreadsheet.
"""

import csv
import io
from datetime import datetime
from typing import Final
from uuid import UUID

from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.errors import InvalidArgumentError, NotFoundError
from azathoth.api.models import SpendGroup, SpendPeriod, SpendReport
from azathoth.persistence.repositories import Repositories
from azathoth.workflows import (
    SpendEntry,
    SpendReportError,
    spend_ledger,
    spend_report,
)


def instance_ledger(repositories: Repositories) -> tuple[SpendEntry, ...]:
    """Return every model call an instance's kept runs and judges made, in the order they ended."""

    return spend_ledger(
        runs=repositories.runs.runs(),
        children_of=repositories.run_children.children_of,
        production_run_ids=frozenset(
            association.run_id for association in repositories.invocation_runs.associations()
        ),
        evaluations=repositories.run_evaluations.evaluations(),
    )


SPEND_CSV_COLUMNS: Final = (
    "period_start",
    "period_end",
    "group",
    "label",
    "billed_usd",
    "estimated_usd",
    "calls",
    "unpriced_calls",
)
"""The header of a spend report written as CSV, in order."""


def spend_csv(report: SpendReport) -> str:
    """Return a spend report as CSV: a header, then a row for each group in each period.

    It is RFC 4180, each line ending in CRLF and any field holding a comma,
    a quote or a line break quoted. Times are ISO 8601 with their offsets,
    and amounts unrounded, so a spreadsheet adds them exactly. A period
    nothing was spent in is one row with no group, so it is never left out.
    """

    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\r\n")
    writer.writerow(SPEND_CSV_COLUMNS)

    for period in report.periods:
        start, end = period.start.isoformat(), period.end.isoformat()

        if not period.groups:
            writer.writerow((start, end, "", "", 0.0, 0.0, 0, 0))

        for group in period.groups:
            writer.writerow(
                (
                    start,
                    end,
                    group.key,
                    group.label,
                    repr(group.billed_usd),
                    repr(group.estimated_usd),
                    group.calls,
                    group.unpriced_calls,
                )
            )

    return text.getvalue()


def spend_command(
    *,
    since: datetime,
    until: datetime,
    period: SpendPeriod,
    group: SpendGroup,
    time_zone: str,
    workflow_id: UUID | None,
) -> str:
    """Return the `azathoth spend` command that prints a report."""

    command = (
        f"azathoth spend --since {since.isoformat()} --until {until.isoformat()}"
        f" --by {period} --group {group} --time-zone {time_zone}"
    )

    return command if workflow_id is None else f"{command} --workflow {workflow_id}"


class Spend:
    """What an instance spent, and when."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
    ) -> None:
        """Read spend from the runs and evaluations `repositories` keep."""

        self._repositories = repositories

    def report(
        self,
        *,
        since: datetime,
        until: datetime,
        period: SpendPeriod = "day",
        group: SpendGroup = "workflow",
        time_zone: str = "UTC",
        workflow_id: UUID | None = None,
    ) -> SpendReport:
        """Return what was spent from `since` up to `until`, by period, in `time_zone`.

        Each period holds its spend by `group`: each workflow, model,
        provider or source. Only `workflow_id`'s calls are counted when it
        is named. It is the `read_spend` action (ADR 0132).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: A time says no offset, `since` is after
                `until`, the period or grouping is not one listed, or the
                time zone is not one.
            NotFoundError: `workflow_id` is neither configured nor made any
                call.
        """

        repositories = self._repositories()
        entries = instance_ledger(repositories)

        if (
            workflow_id is not None
            and repositories.workflows.get(workflow_id) is None
            and not any(entry.workflow_id == workflow_id for entry in entries)
        ):
            raise NotFoundError(f"Workflow {workflow_id} is not configured.")

        try:
            report = spend_report(
                entries,
                since=since,
                until=until,
                period=period,
                group=group,
                time_zone=time_zone,
                workflow_id=workflow_id,
            )
        except SpendReportError as exc:
            raise InvalidArgumentError(str(exc)) from exc

        return SpendReport.model_validate(
            {
                **report.model_dump(),
                "command": spend_command(
                    since=report.since,
                    until=report.until,
                    period=report.period,
                    group=report.group,
                    time_zone=report.time_zone,
                    workflow_id=workflow_id,
                ),
            }
        )


__all__ = [
    "SPEND_CSV_COLUMNS",
    "Spend",
    "instance_ledger",
    "spend_command",
    "spend_csv",
]
