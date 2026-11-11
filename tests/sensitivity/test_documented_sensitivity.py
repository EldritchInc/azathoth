"""Tests that the sensitivity messages the guide quotes are the ones Azathoth gives (ADR 0123)."""

from pathlib import Path

import pytest

from azathoth.api import SENSITIVITY_WITHOUT_INPUT_MESSAGE
from azathoth.cli.rendering.sensitivity import render_sensitivity_lines, restricted_output_warning
from azathoth.sensitivity import (
    RESTRICTED_REFUSAL_HINT,
    UNKNOWN_DATA_POLICY,
    Sensitivity,
    SensitivityError,
    require_no_lower,
    restricted_refusal,
)

README = Path(__file__).parents[2] / "src" / "azathoth" / "sensitivity" / "README.md"

MODEL = "openrouter/example/frontier"


def quoted(
    line: str,
) -> bool:
    return f"\n{line}\n" in README.read_text(encoding="utf-8")


def test_the_lowering_refusal_is_quoted_exactly() -> None:
    with pytest.raises(SensitivityError) as caught:
        require_no_lower(
            Sensitivity.INTERNAL,
            Sensitivity.RESTRICTED,
            source="Run <RUN_ID>",
            derived="a case made from it",
        )

    assert quoted(str(caught.value))


def test_the_restricted_refusal_and_its_hint_are_quoted_exactly() -> None:
    assert quoted(restricted_refusal(MODEL, UNKNOWN_DATA_POLICY))
    assert quoted(RESTRICTED_REFUSAL_HINT.format(model=MODEL))


SENSITIVITY_ADR = Path(__file__).parents[2] / "docs" / "adrs" / "0123-sensitivity-labels.md"

INSTALL_GUIDE = Path(__file__).parents[2] / "docs" / "install.md"


def in_guide(
    guide: Path,
    line: str,
) -> bool:
    return f"\n{line}\n" in guide.read_text(encoding="utf-8")


def test_the_adr_quotes_each_refusal_and_warning_exactly() -> None:
    with pytest.raises(SensitivityError) as caught:
        require_no_lower(
            Sensitivity.INTERNAL,
            Sensitivity.RESTRICTED,
            source="Run <RUN_ID>",
            derived="a case made from it",
        )

    model = "<MODEL>"
    step = (
        f"Step <STEP_ID> sent nothing. {restricted_refusal(model, UNKNOWN_DATA_POLICY)} "
        f"{RESTRICTED_REFUSAL_HINT.format(model=model)}"
    )

    for line in (
        str(caught.value),
        step,
        SENSITIVITY_WITHOUT_INPUT_MESSAGE,
        restricted_output_warning("Run <RUN_ID>"),
    ):
        assert in_guide(SENSITIVITY_ADR, line), line


def test_the_install_guide_quotes_the_warning_and_label_line_exactly() -> None:
    (line,) = render_sensitivity_lines(Sensitivity.RESTRICTED)

    assert in_guide(INSTALL_GUIDE, restricted_output_warning("Run <RUN_ID>"))
    assert in_guide(INSTALL_GUIDE, line)
    assert in_guide(INSTALL_GUIDE, "Restricted Input: allowed")
