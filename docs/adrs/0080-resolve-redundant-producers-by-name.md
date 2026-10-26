# ADR 0080: Resolve Redundant Producers by Name

- Status: Accepted
- Date: 2026-10-25
- Decided in: #100

## Context

A resilient workflow often computes one value two ways: a primary and a
fallback, perhaps a process tool and a Python tool, or two models. Explicit
references name exactly one producer step, so a consumer could not say "take
this value from whichever producer succeeded".

## Decision

Step inputs and the workflow's declared result (ADR 0071) may reference a
value by name alone:

```json
{"name": "count"}
```

A name-only input resolves among the steps its consumer directly depends on
that declare an output with that name. A name-only result resolves among all
steps. In both cases, the first step in declared workflow step order that
actually produced the value supplies it. Producers that were skipped, or that
failed under a tolerant failure policy, are passed over.

Declared step order is chosen over first-to-finish so that the answer is
reproducible.

At least one candidate producer must declare the name, which is validated when
the specification is constructed.

The `workflow.input.bound` event recorded for every value input names the
producer that actually supplied it, so evidence always shows which redundant
producer was used.

Production emissions resolve name-only references the same way.

## Consequences

### Positive

- Redundant producers in one layer can race (ADR 0079), and consumers take
  whichever survived.
- Which producer answered is always recorded.

### Negative

- A name-only reference no longer pins its producer in the specification;
  the evidence, not the specification, says which one supplied a value.

## Alternatives Considered

### Take the first producer to finish

Rejected. The answer would depend on timing.

### Add an explicit fallback list to explicit references

Rejected. Declared step order already expresses preference, without a second
mechanism.
