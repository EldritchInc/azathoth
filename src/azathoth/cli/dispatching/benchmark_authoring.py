"""Dispatch of the commands that create a benchmark and edit its cases (ADR 0130)."""

import sys
from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from azathoth import api
from azathoth.cli.parsing.benchmarks import (
    BENCHMARK_ACTION_ATTRIBUTE,
    BENCHMARK_CASE_COMPARISON_ATTRIBUTE,
    BENCHMARK_CASE_DESCRIPTION_ATTRIBUTE,
    BENCHMARK_CASE_EXPECTED_ATTRIBUTE,
    BENCHMARK_CASE_ID_ATTRIBUTE,
    BENCHMARK_CASE_NO_CITATIONS_ATTRIBUTE,
    BENCHMARK_CASE_ON_UNVERIFIED_ATTRIBUTE,
    BENCHMARK_CASE_REQUIRED_CITATIONS_ATTRIBUTE,
    BENCHMARK_CREATE_ACTION,
    BENCHMARK_DESCRIPTION_ATTRIBUTE,
    BENCHMARK_EDIT_CASE_ACTION,
    BENCHMARK_ID_ATTRIBUTE,
    BENCHMARK_NAME_ATTRIBUTE,
    BENCHMARK_REMOVE_CASE_ACTION,
    BENCHMARK_VERSION_ATTRIBUTE,
)
from azathoth.cli.parsing.workflows import WORKFLOW_INPUT_SENSITIVITY_ATTRIBUTE
from azathoth.evaluation import CitedSegment
from azathoth.sensitivity import Sensitivity

BenchmarkCreateHandler = Callable[..., int]
BenchmarkCaseEditHandler = Callable[..., int]
BenchmarkCaseRemoveHandler = Callable[[UUID, UUID], int]


def dispatch_benchmark_authoring_command(
    arguments: Namespace,
    *,
    create_benchmark: BenchmarkCreateHandler,
    edit_benchmark_case: BenchmarkCaseEditHandler,
    remove_benchmark_case: BenchmarkCaseRemoveHandler,
) -> int | None:
    """Dispatch `benchmark create`, `edit-case` or `remove-case`, or return None for any other."""

    action = cast(str | None, getattr(arguments, BENCHMARK_ACTION_ATTRIBUTE, None))

    if action == BENCHMARK_CREATE_ACTION:
        return create_benchmark(
            name=cast(str, getattr(arguments, BENCHMARK_NAME_ATTRIBUTE)),
            description=cast(str, getattr(arguments, BENCHMARK_DESCRIPTION_ATTRIBUTE)),
            version=cast(str, getattr(arguments, BENCHMARK_VERSION_ATTRIBUTE)),
        )

    if action == BENCHMARK_EDIT_CASE_ACTION:
        on_unverified = cast(
            str | None, getattr(arguments, BENCHMARK_CASE_ON_UNVERIFIED_ATTRIBUTE, None)
        )

        if on_unverified is not None and getattr(
            arguments, BENCHMARK_CASE_NO_CITATIONS_ATTRIBUTE, False
        ):
            print(
                "--on-unverified cannot be given with --no-citations.",
                file=sys.stderr,
            )

            return 1

        return edit_benchmark_case(
            *_case_identity(arguments),
            comparison=cast(
                api.CaseComparison | None,
                getattr(arguments, BENCHMARK_CASE_COMPARISON_ATTRIBUTE, None),
            ),
            expected=_expected(arguments),
            description=cast(
                str | None, getattr(arguments, BENCHMARK_CASE_DESCRIPTION_ATTRIBUTE, None)
            ),
            citations=_citations(arguments, on_unverified),
            sensitivity=cast(
                Sensitivity | None,
                getattr(arguments, WORKFLOW_INPUT_SENSITIVITY_ATTRIBUTE, None),
            ),
        )

    if action == BENCHMARK_REMOVE_CASE_ACTION:
        return remove_benchmark_case(*_case_identity(arguments))

    return None


def _case_identity(
    arguments: Namespace,
) -> tuple[UUID, UUID]:
    """Return the benchmark and the case a command names."""

    return (
        cast(UUID, getattr(arguments, BENCHMARK_ID_ATTRIBUTE)),
        cast(UUID, getattr(arguments, BENCHMARK_CASE_ID_ATTRIBUTE)),
    )


def _expected(
    arguments: Namespace,
) -> JsonValue | api.Keep:
    """Return the expected value an edit gives, or `KEEP` when it gives none.

    The option is absent from the parsed arguments unless it was given, so a
    given JSON null is still an expected value.
    """

    if not hasattr(arguments, BENCHMARK_CASE_EXPECTED_ATTRIBUTE):
        return api.KEEP

    return cast(JsonValue, getattr(arguments, BENCHMARK_CASE_EXPECTED_ATTRIBUTE))


def _citations(
    arguments: Namespace,
    on_unverified: str | None,
) -> api.CaseCitations | None | api.Keep:
    """Return what an edit says the case's run must cite: new segments, nothing, or as it was."""

    if getattr(arguments, BENCHMARK_CASE_NO_CITATIONS_ATTRIBUTE, False):
        return None

    required = cast(
        list[CitedSegment] | None,
        getattr(arguments, BENCHMARK_CASE_REQUIRED_CITATIONS_ATTRIBUTE, None),
    )

    if required is None and on_unverified is None:
        return api.KEEP

    return api.CaseCitations(
        require=tuple(
            api.CitedSegmentSummary(source=cited.source, segment=cited.segment)
            for cited in required or ()
        ),
        on_unverified="ignore" if on_unverified == "ignore" else "fail",
    )


__all__ = [
    "dispatch_benchmark_authoring_command",
]
