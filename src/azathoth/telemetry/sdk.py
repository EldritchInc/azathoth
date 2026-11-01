"""Exporting Azathoth's spans through the OpenTelemetry SDK (ADR 0100).

This module imports the SDK, so it is imported only when tracing is turned
on, and only with the `otel` extra installed.
"""

import importlib
import os
from collections.abc import Callable, Mapping
from typing import Final, cast

from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

from azathoth import __version__
from azathoth.telemetry.otel import OpenTelemetryTelemetry, extract_trace_context

DEFAULT_SERVICE_NAME: Final = "azathoth"
"""The service name spans are exported under unless the environment names one."""

TRACER_NAME: Final = "azathoth"
"""The instrumentation scope of every Azathoth span."""

TRACES_EXPORTER_VARIABLE: Final = "OTEL_TRACES_EXPORTER"

OTLP_EXPORTER: Final = "otlp"
CONSOLE_EXPORTER: Final = "console"
NO_EXPORTER: Final = "none"

SUPPORTED_EXPORTERS: Final = (OTLP_EXPORTER, CONSOLE_EXPORTER, NO_EXPORTER)

_OTLP_HTTP_EXPORTER_MODULE: Final = "opentelemetry.exporter.otlp.proto.http.trace_exporter"


class TelemetryConfigurationError(ValueError):
    """Raised when the environment configures tracing in a way Azathoth does not support."""


def service_resource(
    environ: Mapping[str, str],
) -> Resource:
    """Return the resource spans are exported under.

    `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` are honored; without
    either naming the service, it is `azathoth`. The service version is
    Azathoth's.
    """

    attributes: dict[str, str] = {SERVICE_VERSION: __version__}

    named = environ.get("OTEL_SERVICE_NAME") or "service.name=" in environ.get(
        "OTEL_RESOURCE_ATTRIBUTES", ""
    )

    if not named:
        attributes[SERVICE_NAME] = DEFAULT_SERVICE_NAME

    return Resource.create(attributes)


def span_exporter(
    environ: Mapping[str, str],
) -> SpanExporter | None:
    """Return the exporter `OTEL_TRACES_EXPORTER` names: OTLP over HTTP by default.

    Raises:
        TelemetryConfigurationError: It names an exporter Azathoth does not
            support, such as several at once.
    """

    name = environ.get(TRACES_EXPORTER_VARIABLE, OTLP_EXPORTER).strip().lower() or OTLP_EXPORTER

    if name == NO_EXPORTER:
        return None

    if name == CONSOLE_EXPORTER:
        return ConsoleSpanExporter()

    if name == OTLP_EXPORTER:
        module = importlib.import_module(_OTLP_HTTP_EXPORTER_MODULE)
        exporter_class = cast(Callable[[], SpanExporter], module.OTLPSpanExporter)

        return exporter_class()

    raise TelemetryConfigurationError(
        f"{TRACES_EXPORTER_VARIABLE}={name} is not supported; "
        f"supported exporters: {', '.join(SUPPORTED_EXPORTERS)}."
    )


def tracer_provider(
    environ: Mapping[str, str],
    *,
    processor: SpanProcessor | None = None,
) -> TracerProvider:
    """Return a tracer provider exporting through the environment's exporter in batches.

    A test may pass its own span processor instead.
    """

    provider = TracerProvider(resource=service_resource(environ))

    if processor is None:
        exporter = span_exporter(environ)

        if exporter is not None:
            processor = BatchSpanProcessor(exporter)

    if processor is not None:
        provider.add_span_processor(processor)

    return provider


def sdk_telemetry(
    environ: Mapping[str, str] | None = None,
    *,
    processor: SpanProcessor | None = None,
) -> OpenTelemetryTelemetry:
    """Return telemetry exporting through the SDK, continuing any inherited trace.

    The provider is private to Azathoth rather than installed globally, and
    `shutdown` flushes and stops it.
    """

    source = os.environ if environ is None else environ
    provider = tracer_provider(source, processor=processor)

    return OpenTelemetryTelemetry(
        provider.get_tracer(TRACER_NAME, __version__),
        parent_context=extract_trace_context(source),
        shutdown=provider.shutdown,
    )


__all__ = [
    "CONSOLE_EXPORTER",
    "DEFAULT_SERVICE_NAME",
    "NO_EXPORTER",
    "OTLP_EXPORTER",
    "SUPPORTED_EXPORTERS",
    "TRACER_NAME",
    "TRACES_EXPORTER_VARIABLE",
    "TelemetryConfigurationError",
    "sdk_telemetry",
    "service_resource",
    "span_exporter",
    "tracer_provider",
]
