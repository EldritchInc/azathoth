"""Turning tracing on from the environment (ADR 0100)."""

import os
from collections.abc import Mapping
from typing import Final

from azathoth.telemetry.api import NO_TELEMETRY, Telemetry

OTEL_ENABLED_VARIABLE: Final = "AZATHOTH_OTEL"
"""The variable that turns tracing on: `1`, `true`, `yes` or `on`."""

_ENABLED_VALUES: Final = frozenset({"1", "true", "yes", "on"})

MISSING_EXTRA_MESSAGE: Final = (
    "AZATHOTH_OTEL is set, but OpenTelemetry is not installed; install azathoth-ai[otel]."
)


class TelemetryUnavailableError(RuntimeError):
    """Raised when tracing is turned on without the `otel` extra installed."""

    def __init__(
        self,
    ) -> None:
        super().__init__(MISSING_EXTRA_MESSAGE)


def telemetry_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether the environment turns tracing on."""

    source = os.environ if environ is None else environ

    return source.get(OTEL_ENABLED_VARIABLE, "").strip().lower() in _ENABLED_VALUES


def configure_from_environment(
    environ: Mapping[str, str] | None = None,
) -> Telemetry:
    """Return the telemetry the environment asks for.

    Without `AZATHOTH_OTEL`, it is `NO_TELEMETRY`, and nothing of
    OpenTelemetry is imported. With it, spans are exported through the SDK,
    configured by the standard `OTEL_*` variables.

    Raises:
        TelemetryUnavailableError: Tracing is on, but the `otel` extra is not
            installed.
        TelemetryConfigurationError: The environment names an exporter
            Azathoth does not support.
    """

    source = os.environ if environ is None else environ

    if not telemetry_enabled(source):
        return NO_TELEMETRY

    try:
        from azathoth.telemetry.sdk import sdk_telemetry
    except ImportError as exc:
        raise TelemetryUnavailableError() from exc

    return sdk_telemetry(source)


__all__ = [
    "MISSING_EXTRA_MESSAGE",
    "OTEL_ENABLED_VARIABLE",
    "TelemetryUnavailableError",
    "configure_from_environment",
    "telemetry_enabled",
]
