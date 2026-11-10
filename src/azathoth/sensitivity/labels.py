"""Sensitivity labels, and how the labels of related data combine (ADR 0123)."""

from collections.abc import Iterable
from enum import StrEnum
from typing import Final


class SensitivityError(ValueError):
    """A label is lower than the data it was derived from."""


class Sensitivity(StrEnum):
    """How sensitive data is, from public to restricted.

    Labels are ordered by `rank`, never by their names: as text, `internal`
    sorts before `public`.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"

    @property
    def rank(
        self,
    ) -> int:
        """Return the label's place in the order public, internal, restricted."""

        return _RANKS[self]


_RANKS: Final = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.INTERNAL: 1,
    Sensitivity.RESTRICTED: 2,
}

DEFAULT_SENSITIVITY: Final = Sensitivity.INTERNAL
"""The label of data that names none."""


def effective_sensitivity(
    label: Sensitivity | None,
) -> Sensitivity:
    """Return a label, or `internal` for data that names none."""

    return DEFAULT_SENSITIVITY if label is None else label


def most_sensitive(
    labels: Iterable[Sensitivity | None],
) -> Sensitivity:
    """Return the most sensitive of some labels; an unlabelled one, or none at all, is internal.

    Data derived from several sources is as sensitive as the most sensitive
    of them.
    """

    return max(
        (effective_sensitivity(label) for label in labels),
        key=lambda label: label.rank,
        default=DEFAULT_SENSITIVITY,
    )


def require_no_lower(
    label: Sensitivity | None,
    floor: Sensitivity,
    *,
    source: str,
    derived: str,
) -> None:
    """Refuse a label for derived data lower than the label of what it came from.

    `source` names what it came from and `derived` what it is, as the
    message reads: "Run <ID> is restricted; a case made from it cannot be
    internal." Labels are never lowered by deriving data.

    Raises:
        SensitivityError: The label is lower than `floor`.
    """

    chosen = effective_sensitivity(label)

    if chosen.rank < floor.rank:
        raise SensitivityError(f"{source} is {floor.value}; {derived} cannot be {chosen.value}.")


__all__ = [
    "DEFAULT_SENSITIVITY",
    "Sensitivity",
    "SensitivityError",
    "effective_sensitivity",
    "most_sensitive",
    "require_no_lower",
]
