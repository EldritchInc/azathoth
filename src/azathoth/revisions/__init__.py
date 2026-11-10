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

__all__ = [
    "AUTHOR_EMAIL_PATTERN",
    "AUTHOR_NAME_PATTERN",
    "AUTHOR_VARIABLE",
    "CONTENT_DIGEST_PATTERN",
    "REVISION_DIGEST_FORMAT",
    "Author",
    "AuthorError",
    "Lineage",
    "RevisionKind",
    "content_digest",
    "resolve_author",
    "revision_digest",
]
