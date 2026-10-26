# ADR 0077: Keep Content Digests Stable When Optional Fields Are Added

- Status: Accepted
- Date: 2026-10-25
- Decided in: #100

## Context

ADR 0076 identifies revisions by a digest of their canonical JSON. Adding a
field to a digested model, even an optional one, changes that JSON, and so
changes the digest of every unchanged document.

Re-importing an untouched workflow would then appear as a change, and
"identical to revision N" would stop recognizing true reverts.

## Decision

A digested model drops a new optional field from its serialized form whenever
the field is unset, or off, using a `@model_serializer(mode="wrap")`.

Current uses:

```text
ToolImplementation           command, timeout_seconds
WorkflowStepSpecification    message, emit_values
```

A document that does not use a new field therefore serializes byte for byte
as before, and keeps its digest.

Tests pin the pre-change digests of the checked-in examples, so a change that
breaks stability fails visibly.

The same release also fixes the general rules for adding fields to persisted
models:

- New fields are optional, so earlier records decode. Tests prove it by
  removing the key from dumped JSON.
- An off-by-default flag is a `bool` defaulting to `False`, never
  `bool | None`, so "unset" and "false" cannot diverge.
- When a new field changes a derived meaning, records with the field unset
  keep the old meaning.
- Count and cost fields default to zero, and are rendered only when non-zero,
  so earlier records never display a misleading zero.

Records that are never digested, such as experiment records, still follow the
decoding rules but need no serializer.

## Consequences

### Positive

- Unchanged documents keep their identity across releases.
- Old databases and documents keep working.

### Negative

- Every new optional field on a digested model needs a serializer change and a
  pinned-digest test.

## Alternatives Considered

### Version the digest algorithm

Rejected. Every existing revision would need recomputing, and old and new
digests would be incomparable.

### Accept that new fields change digests

Rejected. Identical content would stop being recognizable as identical.
