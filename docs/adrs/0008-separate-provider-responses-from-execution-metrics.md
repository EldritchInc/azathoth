# ADR 0008: Separate provider responses from execution metrics

## Status

Accepted

## Context

Azathoth executes AI workflows using language model providers, but the
optimization engine should remain independent of any specific provider API.

Different providers expose different response formats and metadata.
Some report token usage, some report latency, some report estimated cost,
and others expose provider-specific information that has no meaning outside
their own SDK.

Execution, evaluation, and optimization should reason about execution
evidence rather than provider implementations.

Coupling execution records directly to provider response models would make
the optimization pipeline dependent on vendor-specific interfaces and make
future provider integrations more difficult.

## Decision

Introduce provider-neutral execution metrics.

Language model providers return provider-specific responses that are
translated into a generic `StrategyExecutionMetrics` model before leaving
the prompting layer.

`StrategyOutcome` carries these metrics through strategy execution.

`StrategyExecutor` records them in `ExecutionResult` without interpreting
their meaning.

Optimization components consume execution metrics rather than provider
responses.

The initial metrics include:

- provider;
- model;
- prompt token count;
- completion token count;
- total token count;
- execution latency;
- estimated execution cost.

## Consequences

Benefits:

- execution remains independent of provider SDKs;
- optimization operates on a stable, provider-neutral representation;
- additional providers can be integrated without modifying execution or
  optimization components;
- future optimization algorithms can compare strategies across quality,
  latency, cost, and token usage using a common data model;
- provider-specific implementation details remain isolated to integration
  layers.

Costs:

- provider responses require an additional translation step;
- provider-specific metadata not represented by
  `StrategyExecutionMetrics` is intentionally discarded unless promoted
  into the common model;
- expanding the common metrics model requires explicit architectural
  evolution.

## Alternatives Considered

### Store provider responses directly in `ExecutionResult`

Rejected.

This would couple execution and optimization to provider-specific response
types, making the core architecture dependent on vendor APIs.

### Preserve only strategy output

Rejected.

Optimization across latency, token usage, provider selection, and execution
cost requires operational measurements in addition to strategy outputs.