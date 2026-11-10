"""The service API the command line calls (ADR 0120).

Commands the API covers call it through the instance this module opens over
the configured database, so the command line, azathoth-mcp and the local
editor share one way to read and change it.
"""

import sys

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.revisions import Author, AuthorError, resolve_author


def service_instance(
    configuration: CliRuntimeConfiguration,
) -> api.Azathoth:
    """Return the service API over the configured database, reaching no provider.

    The instance is made over the command line's own repositories rather
    than opened, so a command treats a database that does not exist yet as
    it always has: an SQLite file is created as it is first used.

    Raises:
        DatabaseUnavailableError: The database is PostgreSQL, and the
            `postgres` extra is not installed.
    """

    return api.Azathoth(repositories(configuration))


def history_line(
    entry: api.WorkflowSummary | api.ToolSummary | api.BenchmarkSummary,
) -> str:
    """Return the start of one history line: revision number, import time and digest prefix."""

    revision = entry.revision
    imported = revision.imported_at.isoformat() if revision.imported_at is not None else "unknown"

    return f"{revision.number}  {imported}  {revision.content_digest[:12]}"


def identical_note(
    entry: api.WorkflowSummary | api.ToolSummary | api.BenchmarkSummary,
) -> str:
    """Return the note ending a history line whose revision reverted to an earlier one."""

    identical = entry.revision.identical_to

    return f"  identical to revision {identical}" if identical is not None else ""


def import_note(
    imported: api.WorkflowDetail | api.ToolDetail | api.BenchmarkDetail,
) -> str:
    """Return the note an import names the earlier revision it is identical to with."""

    identical = imported.revision.identical_to

    return f" (identical to revision {identical})" if identical is not None else ""


def current_author() -> Author | None:
    """Return who a command records as the author, or say why it cannot tell (ADR 0122).

    It is `AZATHOTH_AUTHOR`, or the operating system's username. When neither
    can be used, the reason is printed to standard error and None returned.
    """

    try:
        return resolve_author()
    except AuthorError as exc:
        print(str(exc), file=sys.stderr)

        return None


__all__ = [
    "current_author",
    "history_line",
    "identical_note",
    "import_note",
    "service_instance",
]
