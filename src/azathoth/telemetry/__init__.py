"""Tracing Azathoth with OpenTelemetry, when it is turned on (ADR 0100).

Importing this package imports nothing of OpenTelemetry. The attribute
builders, which depend on Azathoth's workflow and job models, live in
`azathoth.telemetry.attributes`.
"""

from azathoth.telemetry.api import (
    NO_SPAN,
    NO_TELEMETRY,
    Attributes,
    AttributeValue,
    NoTelemetry,
    Telemetry,
    TelemetrySpan,
    active_telemetry,
    traced,
    use_telemetry,
)
from azathoth.telemetry.configuration import (
    MISSING_EXTRA_MESSAGE,
    OTEL_ENABLED_VARIABLE,
    TelemetryUnavailableError,
    configure_from_environment,
    telemetry_enabled,
)
from azathoth.telemetry.conventions import (
    ATTRIBUTE_KEYS,
    INVOCATION_SPAN,
    JOB_SPAN,
    RUN_SPAN,
    SPAN_NAMES,
    STEP_SPAN,
)

__all__ = [
    "ATTRIBUTE_KEYS",
    "INVOCATION_SPAN",
    "JOB_SPAN",
    "MISSING_EXTRA_MESSAGE",
    "NO_SPAN",
    "NO_TELEMETRY",
    "OTEL_ENABLED_VARIABLE",
    "RUN_SPAN",
    "SPAN_NAMES",
    "STEP_SPAN",
    "AttributeValue",
    "Attributes",
    "NoTelemetry",
    "Telemetry",
    "TelemetrySpan",
    "TelemetryUnavailableError",
    "active_telemetry",
    "configure_from_environment",
    "telemetry_enabled",
    "traced",
    "use_telemetry",
]
