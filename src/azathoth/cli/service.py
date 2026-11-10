"""The service API the command line calls (ADR 0120).

Commands the API covers call it through the instance this module opens over
the configured database, so the command line, azathoth-mcp and the local
editor share one way to read and change it.
"""

import sys
from collections.abc import Sequence

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.revisions import Author, AuthorError, LineageRecord, resolve_author


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


def author_note(
    entry: api.WorkflowSummary | api.ToolSummary | api.BenchmarkSummary,
) -> str:
    """Return the note a history line names who imported its revision with (ADR 0122)."""

    author = entry.revision.author

    return f"  by {author.name}" if author is not None else ""


def lineage_lines(
    number: int,
    lineage: Sequence[LineageRecord],
) -> tuple[str, ...]:
    """Return the lines `show` names one revision's digest, parent and author with (ADR 0122).

    The parent is named by its number among the lineage's revisions, or by
    its revision digest when it is not one of them.

    Raises:
        LookupError: The lineage records no revision with that number.
    """

    record = next((candidate for candidate in lineage if candidate.number == number), None)

    if record is None:
        raise LookupError(f"Revision {number} has no lineage record.")

    parent = next(
        (candidate for candidate in lineage if candidate.revision_digest == record.parent_digest),
        None,
    )

    if parent is not None:
        parent_line = f"Parent: revision {parent.number}"
    elif record.parent_digest is not None:
        parent_line = f"Parent: {record.parent_digest}"
    else:
        parent_line = "Parent: none"

    return (
        f"Revision Digest: {record.revision_digest}",
        parent_line,
        f"Author: {record.author}" if record.author is not None else "Author: unknown",
    )


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
    "author_note",
    "current_author",
    "history_line",
    "lineage_lines",
    "identical_note",
    "import_note",
    "service_instance",
]
