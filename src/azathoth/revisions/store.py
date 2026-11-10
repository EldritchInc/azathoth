"""Where the lineage of every revision is kept, in either database (ADR 0122)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from azathoth.persistence import Row, Session, Table, require_integer, require_text
from azathoth.revisions.author import Author
from azathoth.revisions.digest import CONTENT_DIGEST_PATTERN
from azathoth.revisions.lineage import Lineage, RevisionKind, revision_digest

REVISION_LINEAGE: Final = "revision_lineage"
"""The table every revision's lineage is kept in."""

PREVIOUS: Final = "previous"
"""The parent of a revision recorded without one given: the revision numbered before it."""


@dataclass(frozen=True)
class RevisionTable:
    """Where one kind of document keeps its revisions, as the lineage backfill reads them.

    Every revision table holds a lineage ID column, `number` and
    `content_digest`. A tool's also holds its version.
    """

    kind: RevisionKind
    name: str
    id_column: str
    version_column: str | None = None


WORKFLOW_REVISION_TABLE: Final = RevisionTable(
    kind=RevisionKind.WORKFLOW,
    name="workflow_specification_revisions",
    id_column="workflow_id",
)
"""Where workflow specification revisions are kept."""

TOOL_REVISION_TABLE: Final = RevisionTable(
    kind=RevisionKind.TOOL,
    name="tool_document_revisions",
    id_column="tool_id",
    version_column="tool_version",
)
"""Where tool document revisions are kept."""

BENCHMARK_REVISION_TABLE: Final = RevisionTable(
    kind=RevisionKind.BENCHMARK,
    name="benchmark_dataset_revisions",
    id_column="dataset_id",
)
"""Where benchmark dataset revisions are kept."""

REVISION_TABLES: Final = (
    WORKFLOW_REVISION_TABLE,
    TOOL_REVISION_TABLE,
    BENCHMARK_REVISION_TABLE,
)
"""Every table revisions are kept in, in the order the backfill reads them."""


class LineageRecord(BaseModel):
    """Where one revision sits in its lineage, and who authored it.

    A lineage's first revision has no parent. Revisions recorded before
    authors were (before ADR 0122) have no author.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    lineage: Lineage

    number: int = Field(
        ge=1,
    )

    revision_digest: str = Field(
        pattern=CONTENT_DIGEST_PATTERN,
    )

    parent_digest: str | None = Field(
        pattern=CONTENT_DIGEST_PATTERN,
    )

    author: Author | None = None


ParentChoice = Literal["previous"] | LineageRecord | None
"""A revision's parent: the one numbered before it, a recorded revision, or none."""

Revision = TypeVar("Revision")


class BaseRevisionError(ValueError):
    """A revision to build on is not a revision of the lineage being appended to."""


@dataclass(frozen=True)
class SavedRevision(Generic[Revision]):
    """What saving a document did: the revision it is now, where it sits, and whether it is new.

    Saving content identical to the revision it builds on creates nothing:
    the result is that revision, and `created` is false.
    """

    revision: Revision
    lineage: LineageRecord
    created: bool


def child_record(
    lineage: Lineage,
    *,
    number: int,
    content_digest: str,
    parent: LineageRecord | None,
    author: Author | None = None,
) -> LineageRecord:
    """Return the lineage record of a new revision appended on a parent, or as a first one.

    Raises:
        BaseRevisionError: The parent is a revision of another lineage.
    """

    if parent is not None and parent.lineage != lineage:
        raise BaseRevisionError(
            f"Revision {parent.revision_digest} is not a revision of {lineage}."
        )

    parent_digest = None if parent is None else parent.revision_digest

    return LineageRecord(
        lineage=lineage,
        number=number,
        revision_digest=revision_digest(
            lineage,
            content_digest=content_digest,
            parent_digest=parent_digest,
        ),
        parent_digest=parent_digest,
        author=author,
    )


def base_record(
    records: Iterable[LineageRecord],
    lineage: Lineage,
    based_on: str | None,
) -> LineageRecord | None:
    """Return the revision a new one builds on, from a lineage's records.

    Without `based_on` it is the latest revision, or none for a lineage's
    first. With it, it is the revision whose revision digest it is.

    Raises:
        BaseRevisionError: No revision of the lineage has that digest.
    """

    history = tuple(records)

    if based_on is None:
        return max(history, key=lambda record: record.number, default=None)

    for record in history:
        if record.revision_digest == based_on:
            return record

    raise BaseRevisionError(f"Revision {based_on} is not a revision of {lineage}.")


def _fill_revision_lineage(
    session: Session,
    present: frozenset[str],
) -> None:
    """Record the lineage of every revision, in a table being initialized, that lacks one."""

    for table in REVISION_TABLES:
        if table.name in present:
            backfill_lineage(session, table)


REVISION_LINEAGE_TABLES: Final = (
    Table(
        name=REVISION_LINEAGE,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS revision_lineage (
                sequence {sequence},
                kind TEXT NOT NULL,
                lineage_id TEXT NOT NULL,
                lineage_version TEXT NOT NULL,
                number INTEGER NOT NULL,
                revision_digest TEXT NOT NULL,
                parent_digest TEXT,
                author_name TEXT,
                author_email TEXT,
                UNIQUE (
                    kind,
                    lineage_id,
                    lineage_version,
                    number
                ),
                UNIQUE (
                    kind,
                    revision_digest
                )
            )
            """,
        ),
        backfill=_fill_revision_lineage,
    ),
)
"""The table revision lineage is kept in.

Its backfill records the lineage of revisions imported before it existed:
each revision's parent is the one numbered before it, and none has an
author. A workflow's or benchmark's lineage version is stored as the empty
string, so the unique constraints hold in either database.
"""

_SELECT_RECORD: Final = """
    SELECT kind, lineage_id, lineage_version, number, revision_digest, parent_digest,
        author_name, author_email
    FROM revision_lineage
"""


def record_lineage(
    session: Session,
    lineage: Lineage,
    *,
    number: int,
    content_digest: str,
    author: Author | None = None,
    parent: ParentChoice = PREVIOUS,
) -> LineageRecord:
    """Record the lineage of a revision just appended to its lineage, and return it.

    By default its parent is the revision numbered before it, which must
    already be recorded, and the first revision has none. A given parent,
    or None, is used instead: a revision built on an earlier one forks.

    Raises:
        LookupError: The revision numbered before it has no lineage record.
        BaseRevisionError: The given parent is a revision of another lineage.
        IntegrityError: The revision's lineage is already recorded.
    """

    if isinstance(parent, str):
        previous: LineageRecord | None = None

        if number > 1:
            previous = lineage_record(session, lineage, number - 1)

            if previous is None:
                raise LookupError(f"Revision {number - 1} of {lineage} has no lineage record.")

        parent = previous

    record = child_record(
        lineage,
        number=number,
        content_digest=content_digest,
        parent=parent,
        author=author,
    )

    parent_digest = record.parent_digest

    session.execute(
        """
        INSERT INTO revision_lineage (
            kind,
            lineage_id,
            lineage_version,
            number,
            revision_digest,
            parent_digest,
            author_name,
            author_email
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lineage.kind.value,
            str(lineage.id),
            lineage.version or "",
            number,
            record.revision_digest,
            parent_digest,
            None if author is None else author.name,
            None if author is None else author.email,
        ),
    )

    return record


def lineage_record(
    session: Session,
    lineage: Lineage,
    number: int,
) -> LineageRecord | None:
    """Return the lineage record of one numbered revision, if it is recorded."""

    row = session.fetchone(
        _SELECT_RECORD
        + """
        WHERE kind = ? AND lineage_id = ? AND lineage_version = ? AND number = ?
        """,
        (lineage.kind.value, str(lineage.id), lineage.version or "", number),
    )

    return None if row is None else _record(row)


def lineage_records(
    session: Session,
    lineage: Lineage,
) -> tuple[LineageRecord, ...]:
    """Return every recorded revision of a lineage, oldest first."""

    rows = session.fetchall(
        _SELECT_RECORD
        + """
        WHERE kind = ? AND lineage_id = ? AND lineage_version = ?
        ORDER BY number
        """,
        (lineage.kind.value, str(lineage.id), lineage.version or ""),
    )

    return tuple(_record(row) for row in rows)


def revision_by_digest(
    session: Session,
    kind: RevisionKind,
    digest: str,
) -> LineageRecord | None:
    """Return the lineage record of the revision of a kind with this revision digest, if any."""

    row = session.fetchone(
        _SELECT_RECORD
        + """
        WHERE kind = ? AND revision_digest = ?
        """,
        (kind.value, digest),
    )

    return None if row is None else _record(row)


def backfill_lineage(
    session: Session,
    table: RevisionTable,
) -> int:
    """Record the lineage of every revision in a table that has none, and return how many.

    Each lineage's revisions are recorded in number order, so each finds its
    parent recorded before it. None is given an author.

    Raises:
        LookupError: A revision's predecessor is missing from the table.
    """

    version = "''" if table.version_column is None else f"r.{table.version_column}"

    order = (
        f"r.{table.id_column}, r.number"
        if table.version_column is None
        else f"r.{table.id_column}, r.{table.version_column}, r.number"
    )

    rows = session.fetchall(
        f"""
        SELECT r.{table.id_column}, {version}, r.number, r.content_digest
        FROM {table.name} r
        WHERE NOT EXISTS (
            SELECT 1
            FROM revision_lineage l
            WHERE l.kind = ?
                AND l.lineage_id = r.{table.id_column}
                AND l.lineage_version = {version}
                AND l.number = r.number
        )
        ORDER BY {order}
        """,
        (table.kind.value,),
    )

    for row in rows:
        lineage_version = require_text(row[1], "A revision's lineage version was not text.")

        record_lineage(
            session,
            Lineage(
                kind=table.kind,
                id=UUID(require_text(row[0], "A revision's lineage ID was not text.")),
                version=lineage_version or None,
            ),
            number=require_integer(row[2], "A revision number was not an integer."),
            content_digest=require_text(row[3], "A revision's content digest was not text."),
        )

    return len(rows)


def _record(
    row: Row,
) -> LineageRecord:
    """Return the lineage record one row holds."""

    name = row[6]
    email = row[7]

    lineage_version = require_text(row[2], "A lineage version was not text.")

    return LineageRecord(
        lineage=Lineage(
            kind=RevisionKind(require_text(row[0], "A lineage kind was not text.")),
            id=UUID(require_text(row[1], "A lineage ID was not text.")),
            version=lineage_version or None,
        ),
        number=require_integer(row[3], "A lineage revision number was not an integer."),
        revision_digest=require_text(row[4], "A revision digest was not text."),
        parent_digest=(
            None if row[5] is None else require_text(row[5], "A parent digest was not text.")
        ),
        author=(
            None
            if name is None
            else Author(
                name=require_text(name, "An author name was not text."),
                email=None
                if email is None
                else require_text(email, "An author email was not text."),
            )
        ),
    )


def tables_with_lineage(
    tables: Sequence[Table],
) -> tuple[Table, ...]:
    """Return a repository's tables preceded by the revision lineage table.

    A repository that appends revisions prepares this, so the lineage table
    exists whenever it records a revision.
    """

    return (*REVISION_LINEAGE_TABLES, *tables)


__all__ = [
    "BENCHMARK_REVISION_TABLE",
    "PREVIOUS",
    "REVISION_LINEAGE",
    "REVISION_LINEAGE_TABLES",
    "REVISION_TABLES",
    "TOOL_REVISION_TABLE",
    "WORKFLOW_REVISION_TABLE",
    "BaseRevisionError",
    "LineageRecord",
    "ParentChoice",
    "RevisionTable",
    "SavedRevision",
    "backfill_lineage",
    "base_record",
    "child_record",
    "lineage_record",
    "lineage_records",
    "record_lineage",
    "revision_by_digest",
    "tables_with_lineage",
]
