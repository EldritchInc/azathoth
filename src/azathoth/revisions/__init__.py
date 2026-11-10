"""Content identity, lineage and authorship for revisioned durable documents."""

from azathoth.revisions.author import (
    AUTHOR_EMAIL_PATTERN,
    AUTHOR_NAME_PATTERN,
    AUTHOR_VARIABLE,
    Author,
    AuthorError,
    resolve_author,
)
from azathoth.revisions.digest import (
    CONTENT_DIGEST_PATTERN,
    content_digest,
)
from azathoth.revisions.lineage import (
    REVISION_DIGEST_FORMAT,
    Lineage,
    RevisionKind,
    revision_digest,
)
from azathoth.revisions.store import (
    BENCHMARK_REVISION_TABLE,
    REVISION_LINEAGE,
    REVISION_LINEAGE_TABLES,
    REVISION_TABLES,
    TOOL_REVISION_TABLE,
    WORKFLOW_REVISION_TABLE,
    LineageRecord,
    RevisionTable,
    backfill_lineage,
    lineage_record,
    lineage_records,
    record_lineage,
    revision_by_digest,
    tables_with_lineage,
)

__all__ = [
    "AUTHOR_EMAIL_PATTERN",
    "AUTHOR_NAME_PATTERN",
    "AUTHOR_VARIABLE",
    "BENCHMARK_REVISION_TABLE",
    "CONTENT_DIGEST_PATTERN",
    "REVISION_DIGEST_FORMAT",
    "REVISION_LINEAGE",
    "REVISION_LINEAGE_TABLES",
    "REVISION_TABLES",
    "TOOL_REVISION_TABLE",
    "WORKFLOW_REVISION_TABLE",
    "Author",
    "AuthorError",
    "Lineage",
    "LineageRecord",
    "RevisionKind",
    "RevisionTable",
    "backfill_lineage",
    "content_digest",
    "lineage_record",
    "lineage_records",
    "record_lineage",
    "resolve_author",
    "revision_by_digest",
    "revision_digest",
    "tables_with_lineage",
]
