# ADR 0021: Workflow Condition Operators

- Status: Accepted
- Date: 2026-08-10

## Context

Conditional workflow execution allows workflow steps to execute only when upstream workflow values satisfy declared conditions.

The initial condition model supported equality comparison only.

While equality enables basic routing, many practical workflows depend on numeric thresholds or inequality comparisons.

Examples include:

- confidence scores;
- relevance scores;
- latency thresholds;
- document counts;
- evaluation metrics; and
- cost limits.

Supporting these scenarios should not require introducing a general workflow expression language.

## Decision

Workflow conditions now declare an explicit comparison operator.

```text
WorkflowCondition

source
operator
expected
```

Supported operators are:

- Equal
- Not Equal
- Greater Than
- Greater Than or Equal
- Less Than
- Less Than or Equal

Equality operators support all JSON values.

Ordering operators support numeric values only.

Boolean values are intentionally excluded from ordering comparisons even though Python treats them as integers.

Workflow comparison semantics are centralized within `WorkflowCondition`.

The workflow runner resolves workflow values and delegates comparison to the workflow condition rather than implementing comparison logic itself.

## Consequences

### Positive

- Workflow routing supports threshold-based decisions.
- Comparison behavior is centralized.
- WorkflowRunner remains independent of comparison semantics.
- Existing equality conditions remain fully compatible.
- Condition serialization remains stable.
- Additional operators can be introduced without modifying workflow orchestration.

### Negative

- Ordering comparisons are intentionally limited to numeric values.
- Complex expressions such as logical OR or nested conditions remain unsupported.

## Alternatives Considered

### Continue supporting equality only

Rejected because threshold-based workflow routing is a common orchestration requirement.

### Embed comparison logic inside WorkflowRunner

Rejected because comparison semantics belong to workflow conditions rather than orchestration.

### Introduce a workflow expression language

Rejected because comparison operators satisfy current routing requirements while preserving a simple, explicit workflow model.