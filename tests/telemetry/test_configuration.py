"""Tests for turning tracing on from the environment (ADR 0100)."""

import sys

import pytest

from azathoth.telemetry import (
    MISSING_EXTRA_MESSAGE,
    NO_TELEMETRY,
    OTEL_ENABLED_VARIABLE,
    TelemetryUnavailableError,
    configure_from_environment,
    telemetry_enabled,
)


def test_the_switch_is_azathoth_otel() -> None:
    assert OTEL_ENABLED_VARIABLE == "AZATHOTH_OTEL"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
def test_tracing_is_on_for_affirmative_values(
    value: str,
) -> None:
    assert telemetry_enabled({OTEL_ENABLED_VARIABLE: value})


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_tracing_is_off_otherwise(
    value: str,
) -> None:
    assert not telemetry_enabled({OTEL_ENABLED_VARIABLE: value})


def test_tracing_is_off_without_the_variable() -> None:
    assert not telemetry_enabled({})


def test_tracing_off_needs_no_opentelemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk", None)

    assert configure_from_environment({}) is NO_TELEMETRY
    assert configure_from_environment({OTEL_ENABLED_VARIABLE: "0"}) is NO_TELEMETRY


def test_tracing_on_without_the_extra_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    #
    # Without the extra, importing Azathoth's SDK module fails. Blocking that
    # module, rather than the SDK, works even when the SDK is installed and
    # its submodules were already imported by another test.
    #
    monkeypatch.setitem(sys.modules, "azathoth.telemetry.sdk", None)

    with pytest.raises(TelemetryUnavailableError) as raised:
        configure_from_environment({OTEL_ENABLED_VARIABLE: "1"})

    assert str(raised.value) == MISSING_EXTRA_MESSAGE
    assert str(raised.value) == (
        "AZATHOTH_OTEL is set, but OpenTelemetry is not installed; install azathoth-ai[otel]."
    )


def test_importing_the_package_imports_no_opentelemetry() -> None:
    import subprocess

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, azathoth.telemetry; "
            "print(any(name.split('.')[0] == 'opentelemetry' for name in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "False"
