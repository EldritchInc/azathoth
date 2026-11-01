"""Tracing the commands that run workflows (ADR 0100)."""

import contextlib
import sys
from collections.abc import Callable

from azathoth.telemetry import (
    Telemetry,
    TelemetryConfigurationError,
    TelemetryUnavailableError,
    configure_from_environment,
    use_telemetry,
)


def run_traced(
    command: Callable[[Telemetry], int],
) -> int:
    """Run one command with the telemetry the environment asks for, and flush it.

    Tracing is configured before the command does anything, so a command
    asked to trace without the `otel` extra installed, or with an exporter
    Azathoth does not support, runs nothing: it prints why on stderr and
    returns 1.

    While the command runs, its telemetry is the active one, so the process
    tools it runs receive their step's trace context. Its spans are flushed
    before it returns, and a failure to flush never changes its exit status.
    """

    try:
        telemetry = configure_from_environment()
    except (
        TelemetryUnavailableError,
        TelemetryConfigurationError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    previous = use_telemetry(telemetry)

    try:
        return command(telemetry)
    finally:
        use_telemetry(previous)

        with contextlib.suppress(Exception):
            telemetry.shutdown()


__all__ = [
    "run_traced",
]
