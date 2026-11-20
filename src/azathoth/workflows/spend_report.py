"""Spend grouped into periods in a time zone (ADR 0132).

A report covers `since` up to, not including, `until`, by day, ISO week or
month as the clock reads in an IANA time zone, so a day the clocks change
is as long as it was. Every period in the range is listed, spent in or
not, and the first and last are cut to the range. Billed and estimated
dollars are kept apart, never added into one figure, and an unpriced call
is counted, never taken for free.
"""

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Final, Literal, get_args
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

from azathoth.workflows.spend import SpendEntry

SpendPeriod = Literal["day", "week", "month"]
"""How long each period of a report is."""

SpendGroup = Literal["workflow", "model", "provider", "source"]
"""What a report's spend is grouped by within each period."""

SPEND_PERIODS: Final[tuple[SpendPeriod, ...]] = get_args(SpendPeriod)

SPEND_GROUPS: Final[tuple[SpendGroup, ...]] = get_args(SpendGroup)

UNKNOWN_GROUP: Final = "unknown"
"""The group of a call whose model or provider is not recorded."""


class SpendReportError(ValueError):
    """A report was asked for a range, period, grouping or time zone that is not one."""


class SpendTotals(BaseModel):
    """What some calls cost: billed and estimated apart, and how many were unpriced."""

    model_config = ConfigDict(frozen=True)

    billed_usd: float = Field(ge=0.0)
    estimated_usd: float = Field(ge=0.0)
    calls: int = Field(ge=0)
    unpriced_calls: int = Field(ge=0)


class SpendGroupTotals(SpendTotals):
    """What one group's calls cost: a workflow's, a model's, a provider's or a source's."""

    key: str = Field(min_length=1)
    """What the group is: a workflow's ID, `provider/model`, a provider, or a source."""

    label: str = Field(min_length=1)
    """What the group is called: a workflow's name, or else its key."""


class SpendPeriodTotals(BaseModel):
    """One period of a report: when it starts and ends, and what each group spent."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    totals: SpendTotals
    groups: tuple[SpendGroupTotals, ...] = ()


class SpendReport(BaseModel):
    """What was spent from `since` up to `until`, period by period, in a time zone."""

    model_config = ConfigDict(frozen=True)

    since: datetime
    until: datetime
    time_zone: str
    period: SpendPeriod
    group: SpendGroup
    workflow_id: UUID | None = None
    periods: tuple[SpendPeriodTotals, ...]
    groups: tuple[SpendGroupTotals, ...]
    """Each group's spend over every period."""

    totals: SpendTotals


@dataclass
class _Tally:
    """The calls of one period or group, added up as a report is made."""

    billed: list[float] = field(default_factory=list)
    estimated: list[float] = field(default_factory=list)
    calls: int = 0
    unpriced: int = 0
    label: str = ""

    def add(self, entry: SpendEntry) -> None:
        """Count one call, on the side its cost is known by."""

        self.calls += 1

        if entry.cost_usd is None:
            self.unpriced += 1
        elif entry.cost_basis == "billed":
            self.billed.append(entry.cost_usd)
        else:
            self.estimated.append(entry.cost_usd)

    def totals(self) -> SpendTotals:
        """Return what the calls cost, each side summed exactly."""

        return SpendTotals(
            billed_usd=math.fsum(self.billed),
            estimated_usd=math.fsum(self.estimated),
            calls=self.calls,
            unpriced_calls=self.unpriced,
        )

    def group(self, key: str) -> SpendGroupTotals:
        """Return what the calls cost, as the group they are."""

        return SpendGroupTotals(key=key, label=self.label or key, **self.totals().model_dump())


def _zone(time_zone: str) -> ZoneInfo:
    """Return an IANA time zone by its name.

    Raises:
        SpendReportError: It names none.
    """

    try:
        return ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SpendReportError(f"{time_zone!r} is not a time zone.") from exc


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    """Return the moment a day begins in a time zone, as its clock reads it."""

    return datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(zone)


def _first_day(day: date, period: SpendPeriod) -> date:
    """Return the day the period holding `day` begins on."""

    if period == "week":
        return day - timedelta(days=day.weekday())
    if period == "month":
        return day.replace(day=1)

    return day


def _next_day(day: date, period: SpendPeriod) -> date:
    """Return the day the period beginning on `day` ends on."""

    if period == "week":
        return day + timedelta(days=7)
    if period == "month":
        return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)

    return day + timedelta(days=1)


def _periods(
    since: datetime,
    until: datetime,
    period: SpendPeriod,
    zone: ZoneInfo,
) -> Iterator[tuple[datetime, datetime]]:
    """Yield each period of the range, in order, the first and last cut to it."""

    day = _first_day(since.astimezone(zone).date(), period)

    while True:
        start = _midnight(day, zone)

        if start >= until:
            return

        day = _next_day(day, period)
        end = _midnight(day, zone)

        if end > since:
            yield max(start, since).astimezone(zone), min(end, until).astimezone(zone)


def _key(entry: SpendEntry, group: SpendGroup) -> tuple[str, str]:
    """Return the group a call belongs to, and what that group is called."""

    if group == "workflow":
        return str(entry.workflow_id), entry.workflow_name
    if group == "model":
        if entry.provider is None or entry.model is None:
            return UNKNOWN_GROUP, UNKNOWN_GROUP

        name = f"{entry.provider}/{entry.model}"

        return name, name
    if group == "provider":
        provider = entry.provider or UNKNOWN_GROUP

        return provider, provider

    return entry.source, entry.source


def _groups(tallies: dict[str, _Tally]) -> tuple[SpendGroupTotals, ...]:
    """Return each group's totals, in the order of their names."""

    return tuple(
        sorted(
            (tally.group(key) for key, tally in tallies.items()),
            key=lambda each: (each.label, each.key),
        )
    )


def _checked(
    since: datetime,
    until: datetime,
    period: str,
    group: str,
) -> None:
    """Refuse a range, period or grouping a report cannot be made of.

    Raises:
        SpendReportError: Either time says no offset, `since` is after
            `until`, or the period or grouping is not one listed.
    """

    for name, moment in (("since", since), ("until", until)):
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise SpendReportError(f"{name} must say its offset, such as +00:00.")

    if since > until:
        raise SpendReportError("since must not be after until.")
    if period not in SPEND_PERIODS:
        raise SpendReportError("period must be day, week or month.")
    if group not in SPEND_GROUPS:
        raise SpendReportError("group must be workflow, model, provider or source.")


def spend_report(
    entries: Iterable[SpendEntry],
    *,
    since: datetime,
    until: datetime,
    period: SpendPeriod = "day",
    group: SpendGroup = "workflow",
    time_zone: str = "UTC",
    workflow_id: UUID | None = None,
) -> SpendReport:
    """Return what the calls given spent from `since` up to `until`, period by period.

    Only the calls of `workflow_id`, when it is named, are counted. A
    workflow's group is called by the name its latest call recorded.

    Raises:
        SpendReportError: A time with no offset, a `since` after its
            `until`, a period or grouping not listed, or a time zone that
            is not one.
    """

    _checked(since, until, period, group)
    zone = _zone(time_zone)
    bounds = list(_periods(since, until, period, zone))
    periods: list[tuple[_Tally, dict[str, _Tally]]] = [(_Tally(), {}) for _ in bounds]
    overall = _Tally()
    groups: dict[str, _Tally] = {}
    index = 0

    for entry in sorted(entries, key=lambda each: each.at):
        if entry.at < since or entry.at >= until:
            continue
        if workflow_id is not None and entry.workflow_id != workflow_id:
            continue

        while bounds[index][1] <= entry.at:
            index += 1

        key, label = _key(entry, group)
        total, within = periods[index]

        for tally in (
            total,
            within.setdefault(key, _Tally()),
            overall,
            groups.setdefault(key, _Tally()),
        ):
            tally.add(entry)
            tally.label = label

    return SpendReport(
        since=since.astimezone(zone),
        until=until.astimezone(zone),
        time_zone=time_zone,
        period=period,
        group=group,
        workflow_id=workflow_id,
        periods=tuple(
            SpendPeriodTotals(start=start, end=end, totals=total.totals(), groups=_groups(within))
            for (start, end), (total, within) in zip(bounds, periods, strict=True)
        ),
        groups=_groups(groups),
        totals=overall.totals(),
    )


__all__ = [
    "SPEND_GROUPS",
    "SPEND_PERIODS",
    "UNKNOWN_GROUP",
    "SpendGroup",
    "SpendGroupTotals",
    "SpendPeriod",
    "SpendPeriodTotals",
    "SpendReport",
    "SpendReportError",
    "SpendTotals",
    "spend_report",
]
