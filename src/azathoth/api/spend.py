"""What an instance spent, through the service API (ADR 0132).

Spend is a ledger of model calls, each counted once: every kept run's,
production's, and its judges'. A report groups it into periods in a time
zone, billed and estimated apart, and is the `read_spend` action (ADR
0127). `azathoth spend` prints it.
"""

from datetime import datetime
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
    "Spend",
    "instance_ledger",
    "spend_command",
]
