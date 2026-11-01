"""Semantic judge rotation commands for the Azathoth command-line application."""

import sys

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.evaluation import (
    JudgeEntry,
)


def add_judge(
    identifier: str,
) -> int:
    """Append one authorized, currently available model to the judge rotation.

    Judges see benchmark data, so a judge must be a model the organization
    has authorized, exactly like any model a workflow may select.
    """

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    model = runtime.models.get(identifier)

    if model is None:
        print(
            f"Model {identifier!r} is not currently available.",
            file=sys.stderr,
        )

        return 1

    if runtime.portfolio.get(identifier) is None:
        print(
            f"Model {identifier!r} is not authorized.",
            file=sys.stderr,
        )

        return 1

    try:
        repositories(configuration).judges.add(
            JudgeEntry(
                provider=model.provider,
                model=model.model,
            )
        )
    except ValueError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Added judge {identifier}.")

    return 0


def remove_judge(
    identifier: str,
) -> int:
    """Remove one model from the judge rotation.

    Removal reads and writes durable state only, so it works without provider
    credentials, including for a judge whose model is no longer available.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        repositories(configuration).judges.remove(
            identifier,
        )
    except ValueError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Removed judge {identifier}.")

    return 0


def list_judges() -> int:
    """List the judge rotation in order, one identifier per line.

    Listing reads durable state only and does not require provider
    credentials.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    for identifier in repositories(configuration).judges.rotation().identifiers:
        print(identifier)

    return 0


__all__ = [
    "add_judge",
    "list_judges",
    "remove_judge",
]
