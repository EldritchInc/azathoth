# Revisions

`azathoth.revisions` gives revisioned durable documents a shared content
identity.

```python
from azathoth.revisions import (
    CONTENT_DIGEST_PATTERN,
    content_digest,
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
