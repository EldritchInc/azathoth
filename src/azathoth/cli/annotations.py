"""Export the citations a run checked as W3C Web Annotations (ADRs 0117 and 0129).

Each command prints the collection the service API returns, so the JSON is
the same whichever way it is asked for.
"""

import json
import sys
from uuid import UUID

from azathoth import api
from azathoth.api.annotations import GENERATOR
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.service import service_instance


def export_run_annotations(
    run_id: UUID,
) -> int:
    """Print every verified check one run's cited steps kept, as Web Annotations.

    The checks are read from the records the run's journal names, so a run
    still under way exports what its committed steps checked. Only durable
    state is read.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        annotations = service_instance(configuration).runs.annotations(run_id)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    return _print(annotations)


def export_invocation_annotations(
    invocation_id: UUID,
) -> int:
    """Print every verified check one invocation's run kept, as Web Annotations."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        annotations = service_instance(configuration).invocations.annotations(invocation_id)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    return _print(annotations)


def _print(
    annotations: api.Annotations,
) -> int:
    """Print one annotation collection as JSON."""

    print(json.dumps(annotations.collection, ensure_ascii=False, indent=2))

    return 0


__all__ = [
    "GENERATOR",
    "export_invocation_annotations",
    "export_run_annotations",
]
