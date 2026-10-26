# ADR 0071: Declare Each Workflow's Result

- Status: Accepted
- Date: 2026-10-19
- Decided in: #95

## Context

A workflow run produces many values, one or more per step. Benchmarks,
optimization and production all need to know which one is the workflow's
answer.

Guessing, for example by taking the last step's output, breaks as soon as a
workflow has parallel branches, auxiliary steps, or steps that tolerate
failure. Different parts of the lifecycle could also guess differently.

## Decision

`WorkflowSpecification.result` declares the workflow's answer as a
`WorkflowValueReference`: one producer step and one of its declared outputs.

```json
"result": {
  "producer_step_id": "22222222-2222-2222-2222-222222222222",
  "name": "answer"
}
```

The reference is validated when the specification is constructed: the
producer must be a step in the workflow, and the name must be one of its
declared outputs.

The declared result is the one value the rest of the lifecycle treats as the
workflow's outcome:

```text
declared result
      │
      ├── benchmark cases judge it
      ├── optimization experiments judge it
      └── promotion emits it as the production "result" (ADR 0065)
```

`workflow_result` extracts it from a run, and fails with `WorkflowResultError`
when it was not produced.

The field is optional so that workflows stored before results existed still
decode. Every operation that needs an answer (benchmarking, optimization and
promotion) rejects a workflow without one explicitly, before doing any work.

ADR 0080 later adds a name-only form for workflows whose answer can come from
redundant producers.

## Consequences

### Positive

- Every part of the lifecycle judges the same value.
- A misdeclared result fails at construction, not during a run.

### Negative

- Older workflows must declare a result before they can be benchmarked,
  optimized or promoted.

## Alternatives Considered

### Take the last step's output

Rejected. Step order says nothing about which value is the answer.

### Let each benchmark case name the output it judges

Rejected. Cases describe inputs and expectations, not workflow structure, and
any workflow can run against any benchmark.
