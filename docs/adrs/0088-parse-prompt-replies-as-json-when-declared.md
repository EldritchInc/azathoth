# ADR 0088: Parse Prompt Replies as JSON When Declared

- Status: Accepted
- Date: 2026-10-26
- Decided in: #104

## Context

A prompt step's output was always the model's reply text. Output bindings
read values by path, but a path into a string resolves nothing, so later steps
could not use fields of a structured reply: a plan's chapters, a ticket's
category, a review's findings.

The workaround, a tool after every prompt step that parses its reply, doubled
the size of every realistic workflow and taught a pattern worth avoiding.

## Decision

Prompt specifications declare how their reply becomes their output:

```json
"output_format": "json"
```

`PromptOutputFormat` has two values. `text`, the default, returns the reply
unchanged. `json` parses the reply into one JSON value: an object, list,
string, number, boolean or null.

`parse_json_reply` tolerates surrounding whitespace and one surrounding
Markdown code fence, with or without a language tag. Anything else must be
valid JSON.

A reply that does not parse raises `PromptOutputFormatError`:

```text
Prompt strategy '<NAME>' replied with invalid JSON: <reason>.
```

It is a failed attempt, so the step's retry policy applies: a model may reply
in the right shape on a later attempt.

The format is carried from the specification onto every strategy generated
from it, so configured, benchmark, optimized and production candidates behave
identically.

Both specification types serialize without `output_format` when it is `text`,
so existing documents keep their digests (ADR 0077).

The fence handling is written in the prompting package rather than shared with
the semantic judge (ADR 0074), so prompting does not depend on evaluation.

## Consequences

### Positive

- Later steps read structured replies by path.
- Malformed replies are retried like any other attempt failure.
- Existing workflows are unaffected.

### Negative

- Only the reply's syntax is checked. Its shape is not validated against a
  schema; a step that needs a field reads it by path, and fails to resolve it
  when it is missing (ADR 0081).

## Alternatives Considered

### Parse replies with a tool step

Rejected. Every structured prompt step would need a companion step.

### Validate replies against a JSON Schema

Deferred. The `schema` comparison (ADR 0070) already judges shapes in
benchmarks, and syntax is the common need.
