"""Human-readable rendering of what an instance spent (ADR 0132)."""

from azathoth.api import SpendPeriod, SpendPeriodTotals, SpendReport, SpendTotals

UNPRICED_NOTE = "Unpriced calls have no known cost: they are counted, never taken as free."


def _dollars(amount: float) -> str:
    """Return an amount in US dollars, to the millionth."""

    return f"${amount:.6f}"


def _spent(totals: SpendTotals) -> str:
    """Return what some calls cost, billed and estimated apart, and how many there were."""

    calls = f"{totals.calls} call{'' if totals.calls == 1 else 's'}"
    line = (
        f"{_dollars(totals.billed_usd)} billed, {_dollars(totals.estimated_usd)} estimated, {calls}"
    )

    return line if totals.unpriced_calls == 0 else f"{line}, {totals.unpriced_calls} unpriced"


def _period_name(period: SpendPeriodTotals, length: SpendPeriod) -> str:
    """Return a period's name, from the day it starts on in the report's time zone."""

    day = period.start.date()

    if length == "week":
        return f"Week of {day.isoformat()}"
    if length == "month":
        return f"{day.year:04d}-{day.month:02d}"

    return day.isoformat()


def render_spend_report(
    report: SpendReport,
) -> str:
    """Render a spend report: its range, its totals, and each period with its groups.

    Billed and estimated dollars are said apart, never added. A period
    nothing was spent in says so, and unpriced calls are said to be unknown.
    """

    lines = [
        f"Since: {report.since.isoformat()}",
        f"Until: {report.until.isoformat()}",
        f"Time Zone: {report.time_zone}",
        f"Periods: {report.period}",
        f"Grouped By: {report.group}",
    ]

    if report.workflow_id is not None:
        lines.append(f"Workflow ID: {report.workflow_id}")

    lines.extend(
        (
            f"Billed: {_dollars(report.totals.billed_usd)}",
            f"Estimated: {_dollars(report.totals.estimated_usd)}",
            f"Calls: {report.totals.calls}",
            f"Unpriced Calls: {report.totals.unpriced_calls}",
            "",
        )
    )

    for period in report.periods:
        name = _period_name(period, report.period)

        if period.totals.calls == 0:
            lines.append(f"{name}: nothing spent")
            continue

        lines.append(f"{name}: {_spent(period.totals)}")
        lines.extend(f"  {group.label}: {_spent(group)}" for group in period.groups)

    if report.totals.unpriced_calls > 0:
        lines.append(UNPRICED_NOTE)

    return "\n".join(lines)
