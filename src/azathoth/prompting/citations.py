"""Checking what a cited prompt step cites, and keeping the checks (ADR 0116).

A cited step's reply is JSON. Wherever in it an object has exactly the keys
`source`, `segment` and `quote`, each a string, that object is a citation:
of the segment, by its ID, of the extraction the prompt showed under that
source's name. Each is checked against the extraction with no model
involved (ADR 0113), and replaced by its check: the citation as cited, its
`status`, and, when its quote was found, its `anchor`.

Every check of a reply is kept in the content store, as canonical JSON, and
recorded as a `citations` resource of the step, so what the step cited, and
what checking it found, is the engine's record, not the step's word.
"""

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.citations import (
    VERIFIED_STATUSES,
    CitationCheck,
    CitationStatus,
    SegmentedText,
    verify_citation,
)
from azathoth.inputs import ContentStore, InputOrigin
from azathoth.prompting.exceptions import PromptingError
from azathoth.strategies import StrategyResourceBinding

CITATIONS_RESOURCE_KIND: Final = "citations"
"""The kind of resource a cited step records its kept checks as."""

CITATION_KEYS: Final = frozenset({"source", "segment", "quote"})
"""The keys an object of a cited step's reply has exactly when it is a citation."""


class CitationPolicy(BaseModel):
    """How a cited prompt step treats what its reply cites (ADR 0116).

    With `on_unverified` `fail`, the default, a citation whose quote was not
    found fails the attempt, so the step's retry policy asks again; with
    `keep`, its check is kept and recorded, and the step goes on. A quote
    found after normalizing is verified either way.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    on_unverified: Literal["fail", "keep"] = "fail"


class CitationCheckError(PromptingError):
    """Raised when a cited step's reply cites what its prompt did not show, or not truly."""


@dataclass(frozen=True)
class CitedSource:
    """One source a cited prompt showed: its extraction, and where its content lives."""

    segmented: SegmentedText
    origin: InputOrigin | None = None


def check_citations(
    output: JsonValue,
    *,
    sources: Mapping[str, CitedSource],
    policy: CitationPolicy,
    store: ContentStore,
    strategy_name: str,
) -> tuple[JsonValue, StrategyResourceBinding]:
    """Check every citation of a reply; return it with each replaced, and the record.

    Raises:
        CitationCheckError: A citation names a source the prompt did not
            show, or, under `fail`, cites a segment or quote that is not
            there.
    """

    checks: list[dict[str, JsonValue]] = []

    def checked(
        value: JsonValue,
    ) -> JsonValue:
        if isinstance(value, list):
            return [checked(item) for item in value]

        if not isinstance(value, dict):
            return value

        if _is_citation(value):
            check = _check(
                cast(dict[str, str], value),
                sources=sources,
                policy=policy,
                strategy_name=strategy_name,
            )
            checks.append(check)

            return check

        return {key: checked(item) for key, item in value.items()}

    replaced = checked(output)
    record: JsonValue = {"checks": cast(list[JsonValue], checks)}
    digest = store.put(
        json.dumps(
            record,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    )
    counted = Counter(check["status"] for check in checks)

    return (
        replaced,
        StrategyResourceBinding(
            kind=CITATIONS_RESOURCE_KIND,
            identifier=digest,
            attributes={
                "citations": len(checks),
                **{status.value: counted.get(status.value, 0) for status in CitationStatus},
            },
        ),
    )


def _is_citation(
    value: dict[str, JsonValue],
) -> bool:
    """Return whether an object of a reply is a citation."""

    return set(value) == CITATION_KEYS and all(isinstance(value[key], str) for key in value)


def _check(
    citation: dict[str, str],
    *,
    sources: Mapping[str, CitedSource],
    policy: CitationPolicy,
    strategy_name: str,
) -> dict[str, JsonValue]:
    """Check one citation; return it as checked, or refuse it."""

    source, segment, quote = citation["source"], citation["segment"], citation["quote"]
    cited = sources.get(source)

    if cited is None:
        raise CitationCheckError(
            f"Prompt strategy {strategy_name!r} cites source {source!r}, which its prompt "
            "does not show."
        )

    check = verify_citation(
        cited.segmented,
        segment_id=segment,
        quote=quote,
        origin=cited.origin,
    )

    if policy.on_unverified == "fail" and check.status not in VERIFIED_STATUSES:
        raise CitationCheckError(_unverified(check, source=source, strategy_name=strategy_name))

    result: dict[str, JsonValue] = {
        "source": source,
        "segment": segment,
        "quote": quote,
        "status": check.status.value,
    }

    if check.anchor is not None:
        result["anchor"] = cast(
            JsonValue,
            check.anchor.model_dump(mode="json", by_alias=True),
        )

    return result


def _unverified(
    check: CitationCheck,
    *,
    source: str,
    strategy_name: str,
) -> str:
    """Return the message a citation that was not verified fails its attempt with."""

    if check.status is CitationStatus.UNKNOWN_SEGMENT:
        return (
            f"Prompt strategy {strategy_name!r} cites segment {check.segment_id} of source "
            f"{source!r}, which has no such segment."
        )

    return (
        f"Prompt strategy {strategy_name!r} cites {check.quote!r} from segment "
        f"{check.segment_id} of source {source!r}, which the segment does not hold."
    )


__all__ = [
    "CITATIONS_RESOURCE_KIND",
    "CITATION_KEYS",
    "CitationCheckError",
    "CitationPolicy",
    "CitedSource",
    "check_citations",
]
