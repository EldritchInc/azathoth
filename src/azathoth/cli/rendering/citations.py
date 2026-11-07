"""Human-readable rendering of the citations a run's cited steps checked (ADR 0116)."""

from collections.abc import Mapping, Sequence
from typing import NamedTuple
from uuid import UUID

from pydantic import JsonValue


class RecordedCitations(NamedTuple):
    """One cited step's kept record, and the checks it holds, or None when it is not kept."""

    step_id: UUID
    record: str
    checks: tuple[Mapping[str, JsonValue], ...] | None


def render_citation_lines(
    citations: Sequence[RecordedCitations],
) -> list[str]:
    """Return the lines naming every check each cited step of a run kept.

    Each step names its record and how many citations it checked, then each
    check in the order its reply held them: the status, the source, the
    segment, or `-` when none verified it, and the quote, with the pages a
    provider's own citation named. A run with no cited step renders no lines.
    """

    if not citations:
        return []

    lines = ["Citations:"]

    for recorded in citations:
        if recorded.checks is None:
            lines.append(
                f"Step {recorded.step_id}: record {recorded.record} is not in the content store."
            )
            continue

        count = len(recorded.checks)

        lines.append(
            f"Step {recorded.step_id}: {count} citation{'' if count == 1 else 's'}, "
            f"record {recorded.record}"
        )
        lines.extend(f"  {_render_check(check)}" for check in recorded.checks)

    return lines


def _render_check(
    check: Mapping[str, JsonValue],
) -> str:
    """Render one check on one line."""

    segment = check.get("segment")
    rendered = (
        f"{check.get('status')} {check.get('source')} "
        f"{segment if segment is not None else '-'} {check.get('quote')!r}"
    )
    pages = check.get("pages")

    if isinstance(pages, list) and len(pages) == 2:
        first, last = pages
        rendered += f" on page {first}" if first == last else f" on pages {first} to {last}"

    return rendered


__all__ = [
    "RecordedCitations",
    "render_citation_lines",
]
