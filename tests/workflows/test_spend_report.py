"""Tests that spend is grouped into periods in a time zone (ADR 0132)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from azathoth.costs import CostBasis
from azathoth.workflows import (
    SpendEntry,
    SpendReport,
    SpendReportError,
    SpendSource,
    spend_report,
)

NEW_YORK = ZoneInfo("America/New_York")

SUMMARIZE = UUID("5e000000-0000-4000-8000-0000000000a1")

TRANSLATE = UUID("5e000000-0000-4000-8000-0000000000a2")

RUN = UUID("5e000000-0000-4000-8000-0000000000b1")


def at(text: str) -> datetime:
    """Return an instant written in ISO 8601 with its offset."""

    return datetime.fromisoformat(text)


def entry(
    when: str,
    cost: float | None = 1.0,
    *,
    basis: CostBasis | None = "billed",
    source: SpendSource = "run",
    workflow: UUID = SUMMARIZE,
    provider: str | None = "openrouter",
    model: str | None = "acme/small",
) -> SpendEntry:
    """Return one call."""

    return SpendEntry(
        at=at(when),
        source=source,
        workflow_id=workflow,
        workflow_name="summarize" if workflow == SUMMARIZE else "translate",
        run_id=RUN,
        provider=provider,
        model=model,
        cost_usd=cost,
        cost_basis=None if cost is None else basis,
    )


def report(
    *entries: SpendEntry,
    since: str = "2026-11-16T00:00:00-05:00",
    until: str = "2026-11-21T00:00:00-05:00",
    **options: object,
) -> SpendReport:
    """Return the report of the calls given, in New York by default."""

    arguments: dict[str, object] = {"time_zone": "America/New_York", **options}

    return spend_report(entries, since=at(since), until=at(until), **arguments)  # type: ignore[arg-type]


# Periods


def test_a_day_is_a_day_in_the_time_zone_named() -> None:
    spent = report(
        entry("2026-11-19T03:00:00+00:00"),
        entry("2026-11-19T15:00:00+00:00", 2.0),
        since="2026-11-18T00:00:00-05:00",
        until="2026-11-20T00:00:00-05:00",
    )

    assert [(period.start, period.totals.billed_usd) for period in spent.periods] == [
        (at("2026-11-18T00:00:00-05:00"), 1.0),
        (at("2026-11-19T00:00:00-05:00"), 2.0),
    ]
    assert all(period.start.tzinfo == NEW_YORK for period in spent.periods)


def test_the_same_calls_in_utc_fall_on_one_day() -> None:
    spent = report(
        entry("2026-11-19T03:00:00+00:00"),
        entry("2026-11-19T15:00:00+00:00", 2.0),
        since="2026-11-19T00:00:00+00:00",
        until="2026-11-20T00:00:00+00:00",
        time_zone="UTC",
    )

    assert [period.totals.billed_usd for period in spent.periods] == [3.0]


def test_the_time_zone_is_utc_unless_one_is_named() -> None:
    spent = spend_report(
        (), since=at("2026-11-19T00:00:00+00:00"), until=at("2026-11-20T00:00:00+00:00")
    )

    assert spent.time_zone == "UTC"
    assert spent.period == "day"
    assert spent.group == "workflow"


def test_every_period_is_listed_spent_in_or_not() -> None:
    spent = report(entry("2026-11-18T12:00:00-05:00"))

    assert [period.start.day for period in spent.periods] == [16, 17, 18, 19, 20]
    assert [period.totals.calls for period in spent.periods] == [0, 0, 1, 0, 0]
    assert spent.periods[0].groups == ()


def test_the_first_and_last_periods_are_cut_to_the_range() -> None:
    spent = report(since="2026-11-18T10:00:00-05:00", until="2026-11-19T15:30:00-05:00")

    assert [(period.start, period.end) for period in spent.periods] == [
        (at("2026-11-18T10:00:00-05:00"), at("2026-11-19T00:00:00-05:00")),
        (at("2026-11-19T00:00:00-05:00"), at("2026-11-19T15:30:00-05:00")),
    ]


def test_the_range_takes_its_start_and_leaves_out_its_end() -> None:
    spent = report(
        entry("2026-11-16T00:00:00-05:00", 1.0),
        entry("2026-11-21T00:00:00-05:00", 2.0),
        entry("2026-11-15T23:59:59-05:00", 4.0),
    )

    assert spent.totals.billed_usd == 1.0
    assert spent.totals.calls == 1


def test_a_day_the_clocks_go_back_is_25_hours_long() -> None:
    spent = report(since="2026-11-01T00:00:00-04:00", until="2026-11-02T00:00:00-05:00")

    (day,) = spent.periods

    assert (day.start, day.end) == (
        at("2026-11-01T00:00:00-04:00"),
        at("2026-11-02T00:00:00-05:00"),
    )
    assert day.end.astimezone(UTC) - day.start.astimezone(UTC) == timedelta(hours=25)


def test_a_day_the_clocks_go_forward_is_23_hours_long() -> None:
    spent = report(since="2026-03-08T00:00:00-05:00", until="2026-03-09T00:00:00-04:00")

    (day,) = spent.periods

    assert day.end.astimezone(UTC) - day.start.astimezone(UTC) == timedelta(hours=23)


def test_a_week_is_an_iso_week_starting_on_monday() -> None:
    spent = report(
        entry("2026-11-19T12:00:00-05:00"),
        since="2026-11-16T00:00:00-05:00",
        until="2026-11-30T00:00:00-05:00",
        period="week",
    )

    assert [(period.start, period.end) for period in spent.periods] == [
        (at("2026-11-16T00:00:00-05:00"), at("2026-11-23T00:00:00-05:00")),
        (at("2026-11-23T00:00:00-05:00"), at("2026-11-30T00:00:00-05:00")),
    ]
    assert spent.periods[0].start.weekday() == 0


def test_a_week_started_mid_week_begins_at_the_range() -> None:
    spent = report(
        since="2026-11-19T00:00:00-05:00", until="2026-11-24T00:00:00-05:00", period="week"
    )

    assert [period.start for period in spent.periods] == [
        at("2026-11-19T00:00:00-05:00"),
        at("2026-11-23T00:00:00-05:00"),
    ]


def test_a_month_runs_to_the_next_including_across_a_year() -> None:
    spent = report(
        entry("2026-12-31T23:30:00-05:00"),
        since="2026-11-01T00:00:00-04:00",
        until="2027-02-01T00:00:00-05:00",
        period="month",
    )

    assert [(period.start.month, period.end.month) for period in spent.periods] == [
        (11, 12),
        (12, 1),
        (1, 2),
    ]
    assert [period.totals.calls for period in spent.periods] == [0, 1, 0]


# What a period holds


def test_billed_and_estimated_are_kept_apart_and_unpriced_calls_counted() -> None:
    spent = report(
        entry("2026-11-18T12:00:00-05:00", 0.25, basis="billed"),
        entry("2026-11-18T13:00:00-05:00", 0.5, basis="estimated", provider="bedrock"),
        entry("2026-11-18T14:00:00-05:00", None, provider="bedrock"),
        since="2026-11-18T00:00:00-05:00",
        until="2026-11-19T00:00:00-05:00",
    )

    (day,) = spent.periods

    assert (day.totals.billed_usd, day.totals.estimated_usd) == (0.25, 0.5)
    assert (day.totals.calls, day.totals.unpriced_calls) == (3, 1)
    assert spent.totals == day.totals


def test_a_priced_call_with_no_basis_is_estimated_never_billed() -> None:
    spent = report(entry("2026-11-18T12:00:00-05:00", 0.25, basis=None, provider=None, model=None))

    assert (spent.totals.billed_usd, spent.totals.estimated_usd) == (0.0, 0.25)


def test_amounts_are_summed_exactly_never_rounded() -> None:
    spent = report(*(entry("2026-11-18T12:00:00-05:00", 0.1) for _ in range(10)))

    assert spent.totals.billed_usd == 1.0


def test_by_workflow_each_group_is_named_by_its_workflow() -> None:
    spent = report(
        entry("2026-11-18T12:00:00-05:00", 1.0),
        entry("2026-11-18T13:00:00-05:00", 2.0, workflow=TRANSLATE),
        since="2026-11-18T00:00:00-05:00",
        until="2026-11-19T00:00:00-05:00",
    )

    (day,) = spent.periods

    assert [(group.key, group.label, group.billed_usd) for group in day.groups] == [
        (str(SUMMARIZE), "summarize", 1.0),
        (str(TRANSLATE), "translate", 2.0),
    ]


def test_by_model_each_group_is_the_provider_and_model() -> None:
    spent = report(
        entry("2026-11-18T12:00:00-05:00", provider="openrouter", model="acme/small"),
        entry("2026-11-18T13:00:00-05:00", provider="bedrock", model="nova"),
        entry("2026-11-18T14:00:00-05:00", provider=None, model=None),
        group="model",
    )

    assert [group.key for group in spent.groups] == [
        "bedrock/nova",
        "openrouter/acme/small",
        "unknown",
    ]


def test_by_provider_and_by_source() -> None:
    entries = (
        entry("2026-11-18T12:00:00-05:00", provider="openrouter"),
        entry("2026-11-18T13:00:00-05:00", provider="bedrock", source="production"),
        entry("2026-11-18T14:00:00-05:00", provider="openrouter", source="judging"),
    )

    assert [group.key for group in report(*entries, group="provider").groups] == [
        "bedrock",
        "openrouter",
    ]
    assert [group.key for group in report(*entries, group="source").groups] == [
        "judging",
        "production",
        "run",
    ]


def test_the_report_totals_each_group_over_every_period() -> None:
    spent = report(
        entry("2026-11-17T12:00:00-05:00", 1.0),
        entry("2026-11-18T12:00:00-05:00", 2.0),
        entry("2026-11-18T12:00:00-05:00", None),
    )

    (group,) = spent.groups

    assert (group.billed_usd, group.calls, group.unpriced_calls) == (3.0, 3, 1)


def test_one_workflows_spend_alone() -> None:
    spent = report(
        entry("2026-11-18T12:00:00-05:00", 1.0),
        entry("2026-11-18T13:00:00-05:00", 2.0, workflow=TRANSLATE),
        workflow_id=TRANSLATE,
    )

    assert spent.workflow_id == TRANSLATE
    assert spent.totals.billed_usd == 2.0


def test_the_range_is_told_in_the_time_zone() -> None:
    spent = report(since="2026-11-18T05:00:00+00:00", until="2026-11-19T05:00:00+00:00")

    assert (spent.since, spent.until) == (
        at("2026-11-18T00:00:00-05:00"),
        at("2026-11-19T00:00:00-05:00"),
    )
    assert spent.since.tzinfo == NEW_YORK


def test_an_empty_range_has_no_periods() -> None:
    spent = report(since="2026-11-18T00:00:00-05:00", until="2026-11-18T00:00:00-05:00")

    assert spent.periods == ()
    assert spent.totals.calls == 0


# What is refused


def test_a_since_after_its_until_is_refused() -> None:
    with pytest.raises(SpendReportError, match="since must not be after until"):
        report(since="2026-11-19T00:00:00-05:00", until="2026-11-18T00:00:00-05:00")


def test_an_unknown_time_zone_is_refused() -> None:
    with pytest.raises(SpendReportError, match="'Mars/Olympus' is not a time zone"):
        report(time_zone="Mars/Olympus")


def test_a_time_with_no_offset_is_refused() -> None:
    with pytest.raises(SpendReportError, match="since must say its offset"):
        spend_report((), since=datetime(2026, 11, 18), until=datetime(2026, 11, 19, tzinfo=UTC))


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        ("period", "fortnight", "period must be day, week or month"),
        ("group", "colour", "group must be workflow, model, provider or source"),
    ],
)
def test_a_period_or_grouping_not_listed_is_refused(option: str, value: str, message: str) -> None:
    with pytest.raises(SpendReportError, match=message):
        report(**{option: value})


def test_a_spend_report_error_is_a_value_error() -> None:
    assert issubclass(SpendReportError, ValueError)
