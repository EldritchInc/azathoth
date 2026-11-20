"""What an instance spent, on the command line (ADR 0132).

`azathoth spend` prints `spend.report` from the service API: as text, or
as the API's own JSON. A date is its midnight in the report's time zone,
and a time without an offset is read there too. The time zone is this
computer's own unless one is named, and the range the last 30 days
through today unless one is given.
"""

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import render_spend_report
from azathoth.cli.service import service_instance

DEFAULT_DAYS: Final = 30
"""How many days a report covers when its range is not given."""

LOCALTIME: Final = Path("/etc/localtime")


def _zone_named(name: str) -> ZoneInfo | None:
    """Return the IANA time zone `name` names, or None when it names none."""

    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def local_time_zone() -> str:
    """Return the IANA name of this computer's time zone, or UTC when it says none.

    `TZ` names it when it names a zone; otherwise the zone `/etc/localtime`
    links to, as on Linux and macOS.
    """

    named = os.environ.get("TZ", "").removeprefix(":")

    if named and _zone_named(named) is not None:
        return named

    try:
        target = LOCALTIME.resolve().as_posix()
    except OSError:
        return "UTC"

    _, found, key = target.partition("zoneinfo/")

    return key if found and key and _zone_named(key) is not None else "UTC"


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    """Return the moment a day begins in a time zone."""

    return datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(zone)


def _moment(text: str, zone: ZoneInfo, option: str) -> datetime:
    """Return the moment a date or an ISO 8601 time names, read in `zone` without an offset.

    Raises:
        ValueError: It is neither.
    """

    try:
        if len(text) == len("2026-11-01"):
            return _midnight(date.fromisoformat(text), zone)

        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"--{option} must be a date, such as 2026-11-01, "
            f"or a time, such as 2026-11-01T09:00:00-05:00, not {text!r}."
        ) from exc

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=zone)


def spend_command(
    *,
    since: str | None = None,
    until: str | None = None,
    by: str = "day",
    group: str = "workflow",
    time_zone: str | None = None,
    workflow_id: UUID | None = None,
    output_format: str = "text",
) -> int:
    """Print what this instance spent from `since` up to `until`, returning the exit code."""

    name = time_zone if time_zone is not None else local_time_zone()
    zone = _zone_named(name)

    if zone is None:
        print(f"{name!r} is not a time zone.", file=sys.stderr)

        return 1

    try:
        end = (
            _moment(until, zone, "until")
            if until is not None
            else _midnight(datetime.now(zone).date() + timedelta(days=1), zone)
        )
        start = (
            _moment(since, zone, "since")
            if since is not None
            else _midnight(end.astimezone(zone).date() - timedelta(days=DEFAULT_DAYS), zone)
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        report = service_instance(configuration).spend.report(
            since=start,
            until=end,
            period=cast(api.SpendPeriod, by),
            group=cast(api.SpendGroup, group),
            time_zone=name,
            workflow_id=workflow_id,
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(
        report.model_dump_json(indent=2) if output_format == "json" else render_spend_report(report)
    )

    return 0


__all__ = [
    "local_time_zone",
    "spend_command",
]
