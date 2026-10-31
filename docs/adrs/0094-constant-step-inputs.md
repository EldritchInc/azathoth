# ADR 0094: Constant Step Inputs

- Status: Accepted
- Date: 2026-10-31
- Decided in: #111

## Context

A step input binds a name to a source, and every source refers to something
produced at run time: a value from a named producer step, a value by name
alone among redundant producers (ADR 0080), or a field of a context event
such as the workflow input.

A workflow cannot say that an input is simply a known value. The novel
example shows the cost. Each loop's child workflow ID is a constant, but it
lives inside the source of the tool that prepares the loop's settings
(`prepare-chapters`, `prepare-final-edits`, `prepare-revision` and
`pick-edit`), where the workflow document cannot show it and an operator
cannot change it without changing the tool. ADR 0090 recorded this as a
consequence to fix.

## Decision

A step input's source may be a constant JSON value, written in the workflow
document:

```json
{"name": "chapter_workflow_id", "source": {"value": "e1000000-0000-4000-8000-000000000040"}}
```

`{"value": <JSON>}` is a fourth kind of source, beside the producer, named
and context references. Any JSON value may be the constant, including
objects, lists and `null`. The shape is closed: a source with `value` and
any other key is rejected, so a constant cannot be mistaken for a
reference.

At run time a constant is bound exactly like any other input: the step's
context receives a `workflow.input.bound` event with the input's name and
value. Tools receive it as an input and prompt variables bound to the input
render it, with no change to either. The event marks the value as a
constant, and names no producer step, because none produced it.

A constant has no producer and no dependency, so no other rule of the
workflow graph changes.

Only the type of `source` grows. No field is added to any model, so every
existing workflow document serializes exactly as before and keeps its
content digest (ADR 0077).

The input contract (ADR 0096, planned) describes inline input values with a
media type. A constant is an inline value written in the document; when the
contract lands, `media_type` can be added to it as an optional field, with
JSON as the default.

## Consequences

### Positive

- Values a workflow always uses, such as a child workflow's ID or a loop's
  settings, are visible and editable in the workflow document.
- Tools no longer need to hard-code configuration to supply it, and the same
  tool can serve workflows that configure it differently.
- Tools and prompts receive constants through the bound-input mechanism
  they already use.

### Negative

- Changing a constant changes the workflow document, so it is a new revision
  and must be promoted again before production uses it. That is the same
  rule as for every other part of a workflow.
- A constant is a whole input. A tool that needs part of its input fixed and
  part supplied at run time still takes the two as separate inputs.

## Alternatives Considered

### A `constant` field beside `source` on the binding

Rejected. An input would have two ways to say where its value comes from,
and a rule that exactly one is set.

### Workflow-level parameters

Deferred. Named parameters with defaults, set per invocation, describe what
a caller may supply, which is the job of the input and invocation contract.

### Keep configuration in tools

Rejected. It hides the workflow's configuration in tool source and couples
every workflow that uses the tool to the same values.
