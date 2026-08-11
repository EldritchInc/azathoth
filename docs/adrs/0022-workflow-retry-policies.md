# ADR 0022: Workflow Retry Policies

- Status: Accepted
- Date: 2026-08-11

## Context

Workflow execution currently attempts each workflow step exactly once.

In practice, workflow steps frequently interact with external systems such as language models, tool providers, APIs, or network services.

Many failures are transient rather than permanent.

Examples include:

- temporary provider outages;
- rate limiting;
- network interruptions;
- infrastructure failures; and
- transport timeouts.

Retry behavior should be configurable per workflow step without coupling retry semantics to strategy implementations.

Different workflow steps may execute different language models, tools, or external services and therefore require different retry policies.

## Decision

Workflow steps may declare a `WorkflowRetryPolicy`.

Retry policies are immutable and become part of the durable workflow specification.

A retry policy defines:

- maximum attempts;
- initial retry delay;
- exponential backoff multiplier; and
- optional maximum delay.

`max_attempts` represents the total number of execution attempts, including the initial attempt.

For example:

```text
max_attempts = 1

attempt

done
```

```text
max_attempts = 3

attempt
   │
failure
   │
retry
   │
failure
   │
retry
   │
success
```

Workflow retry behavior is implemented by `WorkflowRunner`.

Strategies remain unaware of retry behavior.

The workflow runner retries failed executions until either:

- execution succeeds; or
- the configured number of attempts has been exhausted.

The current implementation computes retry delays but intentionally does not delay execution.

This preserves deterministic execution and fast test suites while establishing the durable retry architecture.

## Consequences

### Positive

- Retry behavior is explicitly configured per workflow step.
- Retry configuration is preserved through workflow specification and candidate generation.
- Workflow orchestration owns retry semantics.
- Strategy implementations remain simple and deterministic.
- Different workflow steps may use different retry policies.
- Retry behavior composes naturally with conditional execution and workflow dependency layers.

### Negative

- Retry delays are currently computed but not applied.
- Retry behavior currently retries every execution failure.
- Retry attempts are not yet surfaced as execution metrics.

## Alternatives Considered

### Retry inside strategies

Rejected because retry behavior is workflow orchestration rather than strategy behavior.

Embedding retries inside strategies would make execution behavior inconsistent across workflow steps.

### Global workflow retry policy

Rejected because different workflow steps frequently interact with different external systems.

Retry behavior should remain step-scoped, matching model bindings, tool bindings, and conditional execution.

### Immediate delay implementation

Rejected because deterministic execution and fast tests are more valuable while establishing the workflow retry architecture.

Delay scheduling can be enabled later without changing workflow specifications.