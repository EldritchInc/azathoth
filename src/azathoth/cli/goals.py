"""Durable goal inspection commands for the Azathoth CLI.

`goal list`, `goal show` and `goal import` go through the service API's
`goals` (ADR 0133), so the command line and every other caller say the
same of an instance's goals. Each prints as it always has.
"""

import sys
from pathlib import Path
from uuid import UUID

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.service import service_instance


def list_goals() -> int:
    """List durable reusable goals."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        goals = service_instance(configuration).goals.list()
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    for goal in goals:
        print(f"{goal.id}  {goal.name}")

    return 0


def show_goal(
    goal_id: UUID,
) -> int:
    """Show one durable reusable goal."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        goal = service_instance(configuration).goals.get(goal_id)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    _print_goal(goal)

    return 0


def _print_goal(
    goal: api.GoalDetail,
) -> None:
    """Render one durable descriptive objective."""

    print(f"ID: {goal.id}")
    print(f"Name: {goal.name}")
    print(f"Description: {goal.description}")

    print("Success Criteria:")

    for criterion in goal.success_criteria:
        print(f"  - {criterion}")

    print("Constraints:")

    if not goal.constraints:
        print("  None")

        return

    for constraint in goal.constraints:
        print(f"  - {constraint}")


def import_goal(
    document_path: Path,
) -> int:
    """Import one durable reusable goal from a JSON document.

    A document that is not a goal is refused before the database is
    touched, and a goal whose ID is taken is never replaced.
    """

    try:
        document = document_path.read_text(
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"Unable to read goal document {document_path}: {exc}",
            file=sys.stderr,
        )

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        imported = service_instance(configuration).goals.import_document(document)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(f"Imported goal {imported.goal.id}.")

    return 0


__all__ = [
    "import_goal",
    "list_goals",
    "show_goal",
]
