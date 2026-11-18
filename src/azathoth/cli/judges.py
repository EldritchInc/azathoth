"""Semantic judge rotation commands for the Azathoth command-line application.

Each command calls the service API (ADR 0129). Adding a judge asks the
providers whether they serve it, so it calls an instance that reaches them;
listing and removing read and write durable state only, so they work
without provider credentials.
"""

import sys

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.service import provider_instance, service_instance


def add_judge(
    identifier: str,
) -> int:
    """Append one authorized, currently available model to the judge rotation.

    Judges see benchmark data, so a judge must be a model the organization
    has authorized, exactly like any model a workflow may select.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        judge = provider_instance(configuration).judges.add(identifier)
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Added judge {judge.identifier}.")

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
        judge = service_instance(configuration).judges.remove(identifier)
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Removed judge {judge.identifier}.")

    return 0


def list_judges() -> int:
    """List the judge rotation in order, one identifier per line.

    Listing reads durable state only and does not require provider
    credentials.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    for judge in service_instance(configuration).judges.list():
        print(judge.identifier)

    return 0


__all__ = [
    "add_judge",
    "list_judges",
    "remove_judge",
]
