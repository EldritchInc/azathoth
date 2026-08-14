# Execution

`azathoth.execution` provides the common execution infrastructure for Azathoth strategies.

Rather than allowing every strategy implementation to manage timing, lifecycle events, execution history, and result construction independently, the execution package provides one deterministic execution pipeline shared by every strategy.

Execution answers one question:

> **What happened when this strategy ran?**

It intentionally does **not** determine whether the output was correct or desirable.

## Purpose

Strategies should focus on behavior.

Execution infrastructure should focus on recording durable evidence.

By separating these concerns, Azathoth gains:

- consistent execution history;
- deterministic lifecycle events;
- provider-neutral execution records;
- immutable execution artifacts; and
- reusable orchestration across every strategy implementation.

## StrategyExecutor

`StrategyExecutor` executes a strategy against a `Context` while recording execution metadata.

```python
from azathoth.execution import StrategyExecutor

executor = StrategyExecutor()

result = await executor.execute(
    strategy=strategy,
    context=context,
)
```

The executor performs the same lifecycle for every strategy.

```text
Initial Context
      │
      ▼
strategy.execution.started
      │
      ▼
Strategy.run()
      │
      ▼
StrategyOutcome
      │
      ▼
Strategy Events
      │
      ▼
strategy.execution.completed
      │
      ▼
ExecutionResult
```

Strategies remain responsible only for producing behavior.

The executor records everything surrounding that behavior.

## Lifecycle Events

Every execution records two standardized lifecycle events.

Execution begins with:

```text
strategy.execution.started
```

and completes with:

```text
strategy.execution.completed
```

Both events include:

- strategy identifier;
- strategy name; and
- strategy version.

Any events produced by the strategy are inserted between those lifecycle events, creating a complete chronological execution history.

## ExecutionResult

Every execution produces an immutable `ExecutionResult`.

It records:

- strategy identifier;
- strategy name;
- strategy version;
- output;
- optional execution metrics;
- initial context;
- final context;
- execution start time; and
- execution completion time.

```text
ExecutionResult
├── Strategy Identity
├── Output
├── Metrics
├── Initial Context
├── Final Context
├── Started At
└── Completed At
```

Execution results become durable evidence used throughout the rest of the system.

## Context Preservation

Execution records both the context received by the strategy and the context after execution completes.

```text
Initial Context
      │
      ▼
 Strategy
      │
      ▼
 Final Context
```

Recording both contexts makes it possible to determine exactly which events were produced during execution.

Workflow execution later uses this property to merge step-local execution events into shared workflow context deterministically.

## Strategy Events

Strategies never modify shared context directly.

Instead, they emit additional `ContextEvent` objects through their `StrategyOutcome`.

The executor appends those events in execution order before recording the completion event.

This keeps execution deterministic while preserving complete provenance.

## Execution Metrics

Strategies may report provider-neutral execution metrics.

Examples include:

- provider;
- model;
- prompt tokens;
- completion tokens;
- total tokens;
- latency; and
- estimated cost.

The executor records these measurements without interpreting them.

Later packages use them for scoring, comparison, and optimization.

## Design Principles

Execution is intentionally:

- deterministic;
- immutable;
- traceable;
- provider independent;
- strategy agnostic; and
- independent of evaluation and optimization.

Execution should faithfully record behavior.

It should never decide whether that behavior was good.

## Typical Flow

```text
Context
   │
   ▼
StrategyExecutor
   │
   ▼
Strategy
   │
   ▼
StrategyOutcome
   │
   ▼
ExecutionResult
```

Execution establishes the durable evidence that later stages analyze.

## Relationship to Other Packages

[`azathoth.context`](../context/README.md) provides the immutable execution state supplied to strategies.

[`azathoth.strategies`](../strategies/README.md) defines the executable contract used by the executor.

[`azathoth.evaluation`](../evaluation/README.md) judges the outputs recorded in execution results.

[`azathoth.workflows`](../workflows/README.md) uses `StrategyExecutor` to execute individual workflow steps while preserving workflow-level execution history.

[`azathoth.optimization`](../optimization/README.md) ultimately compares execution evidence across many candidate strategies and workflows.

See the [project README](../../../README.md) for the complete Azathoth architecture.