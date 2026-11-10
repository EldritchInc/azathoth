"""How show commands name a label, and warn when what they print is restricted (ADR 0123)."""

import sys
from typing import TextIO

from azathoth.sensitivity import DEFAULT_SENSITIVITY, Sensitivity


def render_sensitivity_lines(
    label: Sensitivity,
) -> tuple[str, ...]:
    """Return the line naming a label that is not internal, or none for internal data.

    Data that names no label is internal, so internal data is shown as it
    always was.
    """

    if label is DEFAULT_SENSITIVITY:
        return ()

    return (f"Sensitivity: {label.value}",)


def restricted_output_warning(
    subject: str,
) -> str:
    """Return the warning a command gives when what it prints holds restricted data."""

    return f"{subject} is restricted; its output contains restricted data."


def warn_if_restricted(
    label: Sensitivity,
    subject: str,
    *,
    stream: TextIO | None = None,
) -> None:
    """Warn on standard error that a command's output holds restricted data, when it does.

    `subject` names what is restricted, such as `Run <RUN_ID>`. Nothing is
    redacted: the warning says what the operator is now holding.
    """

    if label is Sensitivity.RESTRICTED:
        print(restricted_output_warning(subject), file=sys.stderr if stream is None else stream)


__all__ = [
    "render_sensitivity_lines",
    "restricted_output_warning",
    "warn_if_restricted",
]
