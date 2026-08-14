# Strategies

`azathoth.strategies` defines the executable behavior of Azathoth.

A strategy is any component capable of consuming a `Context` and producing a `StrategyOutcome`.

The strategy package provides the common execution contract shared by deterministic algorithms, language-model-backed prompting, retrieval systems, tool invocation, planners, and future AI capabilities.

## Purpose

Azathoth separates *what* a system is trying to accomplish from *how* it attempts to accomplish it.

Goals define intent.

Strategies define behavior.

Every executable capability ultimately becomes a strategy.

This common abstraction allows execution, evaluation, workflows, and optimization to operate without knowing how a particular strategy works internally.

## Strategy Protocol

Every strategy exposes stable identifying metadata and asynchronous execution.

```python
from typing import Protocol

from azathoth.context import Context
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
)


class Strategy(Protocol):
    @property
    def metadata(self) -> StrategyMetadata:
        ...

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        ...
```

This protocol intentionally says nothing about prompts, providers, tools, or models.

Those are implementation details.

## Strategy Metadata

Every strategy exposes immutable identifying metadata.

```python
from azathoth.strategies import StrategyMetadata

metadata = StrategyMetadata(
    name="extract-answer",
    description="Extract the latest answer from context.",
)
```

Metadata contains:

- unique identifier;
- name;
- description; and
- version.

This metadata is propagated through execution, experiments, workflow runs, and optimization results so every piece of evidence can be traced back to the strategy that produced it.

## Strategy Outcome

Executing a strategy produces a `StrategyOutcome`.

```python
from azathoth.strategies import StrategyOutcome

outcome = StrategyOutcome(
    output="Hello, world!",
)
```

A strategy outcome may contain:

- a JSON-compatible output;
- additional context events; and
- optional execution metrics.

```text
Strategy
   │
   ▼
StrategyOutcome
   ├── output
   ├── events
   └── metrics
```

Strategies never mutate context directly.

Instead, they may emit additional `ContextEvent` objects that higher-level execution infrastructure records.

## Execution Metrics

Strategies may optionally report provider-neutral execution measurements.

```python
from azathoth.strategies import StrategyExecutionMetrics

metrics = StrategyExecutionMetrics(
    provider="example",
    model="example-model",
    prompt_tokens=100,
    completion_tokens=20,
    total_tokens=120,
    latency_ms=250,
    estimated_cost_usd=0.001,
)
```

Current metrics include:

- provider;
- model;
- prompt tokens;
- completion tokens;
- total tokens;
- latency; and
- estimated cost.

These measurements become part of durable execution history and later contribute to workflow scoring and optimization.

## EventFieldStrategy

`EventFieldStrategy` is Azathoth's deterministic reference strategy.

It extracts one field from the latest matching context event.

```text
Context
   │
   ▼
Latest Matching Event
   │
   ▼
Configured Field
   │
   ▼
StrategyOutcome
```

The extracted value may also be emitted as a new context event, making it available to downstream strategies and workflows.

Although simple, `EventFieldStrategy` demonstrates the complete strategy lifecycle without requiring language models or external services.

## Strategy Errors

Strategy-specific failures derive from `StrategyError`.

Current deterministic failures include:

- `RequiredEventNotFoundError`
- `RequiredFieldNotFoundError`

Higher-level execution systems, such as workflow retry policies, determine how these failures should be handled.

Strategies themselves do not implement retry logic.

## Design Principles

Strategies are intentionally:

- independently executable;
- context driven;
- provider independent at the protocol level;
- immutable where appropriate;
- traceable through metadata; and
- compatible with shared execution infrastructure.

Strategies describe behavior.

They do not own execution orchestration, evaluation policy, workflow composition, or optimization logic.

## Typical Flow

```text
Context
   │
   ▼
Strategy
   │
   ▼
StrategyOutcome
   ├── Output
   ├── Events
   └── Metrics
```

Execution infrastructure records this outcome and transforms it into durable execution evidence.

## Relationship to Other Packages

[`azathoth.context`](../context/README.md) supplies the immutable working state consumed by strategies.

[`azathoth.execution`](../execution/README.md) executes strategies while recording lifecycle events, timing information, and execution history.

[`azathoth.prompting`](../prompting/README.md) implements language-model-backed strategies using this common protocol.

[`azathoth.workflows`](../workflows/README.md) composes multiple strategies into dependency-driven executable workflows.

[`azathoth.optimization`](../optimization/README.md) compares competing strategies empirically using reproducible experiments.

See the [project README](../../../README.md) for the complete Azathoth architecture.