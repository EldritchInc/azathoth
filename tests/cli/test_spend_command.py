"""Tests for `azathoth spend`, which prints what an instance spent (ADR 0132)."""

import csv
import io
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from azathoth import api
from azathoth.cli import local_time_zone, spend_command
from azathoth.cli.parsing import build_parser
from azathoth.persistence.repositories import Repositories, open_repositories
from tests.api.test_spend import OTHER, WORKFLOW, keep
from tests.cli.test_experiment_commands import configure_database

NEW_YORK = "America/New_York"

UNKNOWN_ID = UUID("00000000-0000-4000-8000-0000000000ff")


@pytest.fixture
def stored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Repositories:
    """Return the repositories of the CLI's database."""

    return open_repositories(str(configure_database(monkeypatch, tmp_path)))


def spent(
    capsys: pytest.CaptureFixture[str],
    **options: object,
) -> api.SpendReport:
    """Run the command as JSON, returning the report it printed."""

    arguments: dict[str, object] = {
        "since": "2026-11-18",
        "until": "2026-11-20",
        "time_zone": NEW_YORK,
        "output_format": "json",
        **options,
    }

    assert spend_command(**arguments) == 0  # type: ignore[arg-type]

    return api.SpendReport.model_validate_json(capsys.readouterr().out)


# Parsing


def test_the_command_parses_with_its_defaults() -> None:
    arguments = build_parser().parse_args(["spend"])

    assert (arguments.spend_since, arguments.spend_until) == (None, None)
    assert (arguments.spend_by, arguments.spend_group) == ("day", "workflow")
    assert (arguments.spend_time_zone, arguments.spend_workflow) == (None, None)
    assert (arguments.spend_output, arguments.spend_output_file) == ("text", None)


def test_the_command_parses_every_option() -> None:
    arguments = build_parser().parse_args(
        [
            "spend",
            "--since",
            "2026-11-01",
            "--until",
            "2026-12-01",
            "--by",
            "week",
            "--group",
            "model",
            "--time-zone",
            NEW_YORK,
            "--workflow",
            str(WORKFLOW.id),
            "--output",
            "csv",
            "--output-file",
            "spend.csv",
        ]
    )

    assert (arguments.spend_since, arguments.spend_until) == ("2026-11-01", "2026-12-01")
    assert (arguments.spend_by, arguments.spend_group) == ("week", "model")
    assert (arguments.spend_time_zone, arguments.spend_workflow) == (NEW_YORK, WORKFLOW.id)
    assert (arguments.spend_output, arguments.spend_output_file) == ("csv", Path("spend.csv"))


@pytest.mark.parametrize(("option", "value"), [("--by", "fortnight"), ("--group", "colour")])
def test_a_period_or_grouping_not_listed_is_refused_as_it_is_parsed(
    option: str, value: str
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["spend", option, value])


# The range


def test_a_date_is_its_midnight_in_the_time_zone(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = spent(capsys)

    assert report.since.isoformat() == "2026-11-18T00:00:00-05:00"
    assert report.until.isoformat() == "2026-11-20T00:00:00-05:00"


def test_a_time_keeps_its_offset_and_one_without_is_read_in_the_time_zone(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = spent(capsys, since="2026-11-18T05:00:00+00:00", until="2026-11-19T09:30:00")

    assert report.since.isoformat() == "2026-11-18T00:00:00-05:00"
    assert report.until.isoformat() == "2026-11-19T09:30:00-05:00"


def test_by_default_it_reports_the_last_30_days_through_today(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = spent(capsys, since=None, until=None)
    tomorrow = datetime.now(ZoneInfo(NEW_YORK)).date() + timedelta(days=1)

    assert report.until.date() == tomorrow
    assert (report.until.hour, report.until.minute) == (0, 0)
    assert report.until.date() - report.since.date() == timedelta(days=30)
    assert len(report.periods) == 30


def test_the_time_zone_is_the_computers_own_unless_one_is_named(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TZ", "Asia/Tokyo")

    assert local_time_zone() == "Asia/Tokyo"
    assert spent(capsys, time_zone=None).time_zone == "Asia/Tokyo"


def test_a_time_zone_named_by_tz_that_is_not_one_is_passed_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TZ", "Mars/Olympus")

    assert local_time_zone() != "Mars/Olympus"


# Text


def test_it_prints_the_range_the_totals_and_each_period(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep(stored, "2026-11-18T12:00:00-05:00", 0.25)
    keep(stored, "2026-11-18T13:00:00-05:00", 0.5, basis="estimated", provider="bedrock")

    assert spend_command(since="2026-11-18", until="2026-11-20", time_zone=NEW_YORK) == 0

    assert capsys.readouterr().out.splitlines() == [
        "Since: 2026-11-18T00:00:00-05:00",
        "Until: 2026-11-20T00:00:00-05:00",
        f"Time Zone: {NEW_YORK}",
        "Periods: day",
        "Grouped By: workflow",
        "Billed: $0.250000",
        "Estimated: $0.500000",
        "Calls: 2",
        "Unpriced Calls: 0",
        "",
        "2026-11-18: $0.250000 billed, $0.500000 estimated, 2 calls",
        "  summarize: $0.250000 billed, $0.500000 estimated, 2 calls",
        "2026-11-19: nothing spent",
    ]


def test_unpriced_calls_are_counted_and_said_to_be_unknown(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep(stored, "2026-11-18T12:00:00-05:00", None, provider="bedrock")

    assert spend_command(since="2026-11-18", until="2026-11-19", time_zone=NEW_YORK) == 0

    out = capsys.readouterr().out.splitlines()

    assert "Unpriced Calls: 1" in out
    assert "2026-11-18: $0.000000 billed, $0.000000 estimated, 1 call, 1 unpriced" in out
    assert out[-1] == "Unpriced calls have no known cost: they are counted, never taken as free."


def test_weeks_and_months_are_named_by_their_start(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep(stored, "2026-11-18T12:00:00-05:00", 0.25)

    assert spend_command(since="2026-11-16", until="2026-11-23", by="week", time_zone=NEW_YORK) == 0
    assert "Week of 2026-11-16: $0.250000 billed, $0.000000 estimated, 1 call" in (
        capsys.readouterr().out.splitlines()
    )

    assert (
        spend_command(since="2026-11-01", until="2026-12-01", by="month", time_zone=NEW_YORK) == 0
    )
    assert "2026-11: $0.250000 billed, $0.000000 estimated, 1 call" in (
        capsys.readouterr().out.splitlines()
    )


def test_one_workflows_spend_names_it(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep(stored, "2026-11-18T12:00:00-05:00", 0.25)
    keep(stored, "2026-11-18T13:00:00-05:00", 0.5, workflow=OTHER)

    assert (
        spend_command(
            since="2026-11-18", until="2026-11-19", time_zone=NEW_YORK, workflow_id=OTHER.id
        )
        == 0
    )

    out = capsys.readouterr().out.splitlines()

    assert f"Workflow ID: {OTHER.id}" in out
    assert "Billed: $0.500000" in out


# JSON


def test_json_is_the_service_apis_report(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep(stored, "2026-11-18T12:00:00-05:00", 0.25)

    report = spent(capsys, group="model")

    assert report.group == "model"
    assert [group.key for group in report.groups] == ["openrouter/acme/small"]
    assert report.totals.billed_usd == 0.25


# CSV and files


def test_csv_is_a_row_per_group_in_each_period(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep(stored, "2026-11-18T12:00:00-05:00", 0.25)

    assert (
        spend_command(
            since="2026-11-18", until="2026-11-20", time_zone=NEW_YORK, output_format="csv"
        )
        == 0
    )

    out = capsys.readouterr().out
    rows = list(csv.DictReader(io.StringIO(out, newline="")))

    assert out.splitlines()[0] == ",".join(api.SPEND_CSV_COLUMNS)

    assert [(row["period_start"], row["label"], row["billed_usd"]) for row in rows] == [
        ("2026-11-18T00:00:00-05:00", "summarize", "0.25"),
        ("2026-11-19T00:00:00-05:00", "", "0.0"),
    ]


@pytest.mark.parametrize("output_format", ["text", "json", "csv"])
def test_a_report_is_written_to_the_file_named_and_printed_nowhere(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    output_format: str,
) -> None:
    keep(stored, "2026-11-18T12:00:00-05:00", 0.25)
    path = tmp_path / f"spend.{output_format}"

    assert (
        spend_command(
            since="2026-11-18",
            until="2026-11-20",
            time_zone=NEW_YORK,
            output_format=output_format,
            output_file=path,
        )
        == 0
    )

    captured = capsys.readouterr()
    written = path.read_bytes().decode("utf-8")

    assert captured.out == ""
    assert captured.err.strip() == f"Wrote the report to {path}."

    if output_format == "csv":
        assert written.splitlines()[0].startswith("period_start,period_end,")
        assert "\r\n" in written
    elif output_format == "json":
        assert api.SpendReport.model_validate_json(written).totals.billed_usd == 0.25
    else:
        assert written.startswith("Since: 2026-11-18T00:00:00-05:00\n")


def test_a_file_that_cannot_be_written_is_refused(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "spend.csv"

    assert spend_command(time_zone=NEW_YORK, output_format="csv", output_file=path) == 1
    assert capsys.readouterr().err.startswith(f"Couldn't write the report to {path}: ")


# What it refuses


@pytest.mark.parametrize("option", ["since", "until"])
def test_a_range_that_is_not_a_date_or_a_time_is_refused(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
    option: str,
) -> None:
    arguments: dict[str, object] = {
        "since": "2026-11-18",
        "until": "2026-11-20",
        "time_zone": NEW_YORK,
        option: "next tuesday",
    }

    assert spend_command(**arguments) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().err.strip() == (
        f"--{option} must be a date, such as 2026-11-01, "
        "or a time, such as 2026-11-01T09:00:00-05:00, not 'next tuesday'."
    )


def test_a_since_after_its_until_is_refused(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert spend_command(since="2026-11-20", until="2026-11-18", time_zone=NEW_YORK) == 1
    assert capsys.readouterr().err.strip() == "since must not be after until."


def test_an_unknown_time_zone_is_refused(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert spend_command(time_zone="Mars/Olympus") == 1
    assert capsys.readouterr().err.strip() == "'Mars/Olympus' is not a time zone."


def test_an_unknown_workflow_is_refused(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert spend_command(time_zone=NEW_YORK, workflow_id=UNKNOWN_ID) == 1
    assert capsys.readouterr().err.strip() == f"Workflow {UNKNOWN_ID} is not configured."
