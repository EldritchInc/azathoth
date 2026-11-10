# Revisions

`azathoth.revisions` gives revisioned durable documents a shared content
identity, the lineage their revisions belong to, and who authored them.

```python
from azathoth.revisions import (
    AUTHOR_VARIABLE,
    CONTENT_DIGEST_PATTERN,
    Author,
    AuthorError,
    Lineage,
    RevisionKind,
    content_digest,
    resolve_author,
    revision_digest,
)
```

`content_digest(document)` returns the sha256 hex digest of a document's
canonical JSON: its JSON-mode dump with sorted keys and no insignificant
whitespace. Two documents with the same digest describe the same content,
whatever the key order or formatting of the files they were imported from.

Workflow specifications, tool documents, and benchmark datasets are imported
as numbered revisions under a stable lineage ID. Each revision records its
digest, which is how a re-import is recognized as identical to an earlier
revision, and how saved evidence names the exact content it ran:

```text
workflow import / tool import / benchmark import
        │
        ▼
revision N, content_digest
        │
        ▼
runs, tool bindings, experiments, and benchmark executions
```

A digest records content as it was imported. A later version of Azathoth that
adds fields to a document model may digest the same file differently, so
stored digests are compared, never recomputed and checked.

## Lineages and revision digests

A `Lineage` is what revisions are appended under: a workflow ID, a benchmark
dataset ID, or a tool ID and exact version (ADR 0122).

`revision_digest(lineage, content_digest=..., parent_digest=...)` identifies
one revision wherever it is kept. It is the sha256 hex digest of the
revision's canonical identity, JSON with sorted keys and no insignificant
whitespace:

```json
{"content":"<content digest>","format":1,"id":"<lineage ID>","kind":"workflow","parent":"<parent revision digest or null>","version":null}
```

Because each revision digest covers its parent's, it covers the revision's
whole history, as a git commit does. Two instances holding a revision with the
same digest hold the same content reached by the same revisions. A revert is
a new revision: its content digest matches the revision it reverts to, and its
revision digest does not.

## Authors

Every new revision records its `Author`, a name and an optional email. The
author is never part of a digest, so the same work imported by two people is
one revision. `resolve_author()` takes the first of these that is set:

1. `AZATHOTH_AUTHOR`, as `Name <email>` or `Name`. Empty counts as unset.
2. The operating system's username, without an email.

A malformed `AZATHOTH_AUTHOR` is refused rather than ignored:

```text
AZATHOTH_AUTHOR is '<value>'; set it to "Name <email>" or "Name".
Could not tell who is importing; set AZATHOTH_AUTHOR to "Name <email>" or "Name".
```
