# ADR 0003: Separate strategy behavior from execution orchestration

## Status

Accepted

## Context

Every Azathoth strategy must eventually support consistent operational
behavior, including:

- lifecycle tracing;
- timing;
- failure recording;
- retries;
- cost measurement;
- cancellation;
- provider telemetry.

Embedding those concerns inside every strategy would duplicate logic and make
execution traces inconsistent.

## Decision

Strategies will implement only their domain operation through the `Strategy`
protocol.

A separate `StrategyExecutor` will manage execution concerns and return a
complete `ExecutionResult`.

Strategies return a `StrategyOutcome` containing:

- their direct output;
- any domain events they produced.

The executor records:

- the initial context;
- strategy execution start;
- strategy-produced events;
- strategy execution completion;
- the final context;
- execution timestamps.

## Consequences

Benefits:

- strategy implementations remain focused;
- lifecycle behavior is consistent;
- deterministic and model-backed strategies share one interface;
- tracing can evolve without changing every strategy;
- execution services can later add retries and telemetry.

Costs:

- direct strategy calls bypass executor tracing;
- additional models exist between strategy and caller;
- failure behavior must be designed explicitly in a later increment.