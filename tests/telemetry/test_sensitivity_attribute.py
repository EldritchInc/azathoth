"""Tests that a run's span names its label, and only its label (ADR 0123)."""

import pytest

from azathoth.context import Context, create_input_sensitivity_event
from azathoth.sensitivity import Sensitivity
from azathoth.telemetry import ATTRIBUTE_KEYS
from azathoth.telemetry.attributes import run_attributes
from azathoth.telemetry.conventions import SENSITIVITY
from tests.telemetry.test_attributes import create_run


def test_the_label_attribute_is_named() -> None:
    assert SENSITIVITY == "azathoth.sensitivity"
    assert SENSITIVITY in ATTRIBUTE_KEYS


@pytest.mark.parametrize("label", list(Sensitivity))
def test_a_runs_span_names_its_label(
    label: Sensitivity,
) -> None:
    context = Context(events=(create_input_sensitivity_event(label, producer="test"),))
    run = create_run(revision=1).model_copy(update={"initial_context": context})

    assert run_attributes(run)[SENSITIVITY] == label.value


def test_an_unlabelled_runs_span_names_it_internal() -> None:
    assert run_attributes(create_run(revision=1))[SENSITIVITY] == "internal"
