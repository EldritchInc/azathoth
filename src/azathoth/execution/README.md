# Execution

`azathoth.execution` provides Azathoth's common strategy execution boundary.

Execution takes an executable `Strategy` and immutable `Context`, records the
successful execution lifecycle, and returns an immutable `ExecutionResult`.

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

The execution package answers:

```text
What happened when this strategy successfully executed?
```

It does not answer:

```text
Was the result correct?

Was the result good?

Should it be retried?

Should another strategy be preferred?

Should this behavior be promoted?
```

Those questions belong to other Azathoth domains.

## Architectural Role

Strategies define executable behavior.

Execution infrastructure records that behavior consistently.

```text
Strategy
    behavior

StrategyExecutor
    execution lifecycle

ExecutionResult
    recorded evidence
```

The V1 execution package deliberately contains only two public concepts:

- `StrategyExecutor`
- `ExecutionResult`

This narrow surface keeps strategy execution separate from workflow
orchestration, evaluation, optimization, and persistence.

# Public Surface

The V1 package exports:

```python
from azathoth.execution import (
    ExecutionResult,
    StrategyExecutor,
)
```

There are no execution repositories, evaluation policies, retry policies, or
provider-specific executors in this package.

# StrategyExecutor

`StrategyExecutor` executes any object satisfying Azathoth's common `Strategy`
protocol.

```python
executor = StrategyExecutor()

result = await executor.execute(
    strategy,
    context,
)
```

Its inputs are:

```text
Strategy

Context
```

Its successful output is:

```text
ExecutionResult
```

The executor does not need to know whether the strategy is:

```text
deterministic

prompt-backed

tool-backed

or another Strategy implementation
```

It depends only on the shared strategy contract.

# Execution Lifecycle

A successful execution follows one deterministic lifecycle:

```text
Initial Context
      │
      ▼
record started_at
      │
      ▼
strategy.execution.started
      │
      ▼
append start event
      │
      ▼
Strategy.run()
      │
      ▼
StrategyOutcome
      │
      ▼
append outcome events in order
      │
      ▼
record completed_at
      │
      ▼
strategy.execution.completed
      │
      ▼
append completion event
      │
      ▼
Final Context
      │
      ▼
ExecutionResult
```

The executor therefore surrounds strategy behavior with standardized execution
evidence.

# Start Time

Immediately before strategy execution, the executor obtains:

```text
started_at
```

from its configured clock.

By default the clock returns the current timezone-aware UTC time.

The clock is injectable, which allows deterministic tests and application
composition without changing execution semantics.

```text
clock()
   │
   ▼
started_at
```

# Start Lifecycle Event

The executor creates:

```text
strategy.execution.started
```

before invoking the strategy.

Its payload contains:

```text
strategy_id

strategy_name

strategy_version
```

and its producer is:

```text
strategy-executor
```

Its occurrence time is the same `started_at` value recorded on the eventual
`ExecutionResult`.

Conceptually:

```text
StrategyMetadata
      │
      ▼
strategy.execution.started
      │
      ▼
execution Context
```

# Strategy Receives Execution Context

The executor does not call the strategy with the original context unchanged.

It first appends the start event:

```text
initial Context
      │
      +
strategy.execution.started
      │
      ▼
execution Context
```

and passes that resulting context to:

```python
await strategy.run(execution_context)
```

A strategy can therefore observe that it is executing inside the standardized
execution lifecycle.

# StrategyOutcome

The strategy returns a `StrategyOutcome`.

```text
StrategyOutcome
├── output
├── events
└── metrics
```

The outcome is the direct result of strategy behavior.

It is not yet the complete execution record.

The distinction remains:

```text
StrategyOutcome
    direct behavior result

ExecutionResult
    recorded execution evidence
```

# Strategy-Produced Events

Any events returned through:

```text
StrategyOutcome.events
```

are appended to the execution context in declaration order.

```text
strategy.execution.started
          │
          ▼
strategy event A
          │
          ▼
strategy event B
          │
          ▼
strategy event C
```

The executor does not reorder these events.

This preserves explicit strategy-produced history.

# Completion Time

After the strategy returns and its events have been appended, the executor
obtains:

```text
completed_at
```

from the configured clock.

This occurs before the completion lifecycle event is constructed.

# Completion Lifecycle Event

The executor then appends:

```text
strategy.execution.completed
```

with the same strategy identity fields used by the start event:

```text
strategy_id

strategy_name

strategy_version
```

Its producer is:

```text
strategy-executor
```

and its occurrence timestamp is:

```text
completed_at
```

The successful context history therefore has the shape:

```text
existing context events
        │
        ▼
strategy.execution.started
        │
        ▼
strategy-emitted events
        │
        ▼
strategy.execution.completed
```

# ExecutionResult

A successful execution produces an immutable `ExecutionResult`.

It records:

```text
strategy_id

strategy_name

strategy_version

output

metrics

initial_context

final_context

started_at

completed_at
```

Conceptually:

```text
ExecutionResult
├── strategy identity
├── output
├── optional metrics
├── initial Context
├── final Context
├── started_at
└── completed_at
```

This object is the execution package's evidence boundary.

# Strategy Identity Is Captured

`ExecutionResult` copies the executing strategy's:

```text
id

name

version
```

from `StrategyMetadata`.

This means execution evidence remains identifiable even when the caller no
longer holds the original live strategy object.

```text
Strategy
   │
   ▼
StrategyMetadata
   │
   ▼
ExecutionResult
```

# Output Is Recorded, Not Interpreted

`ExecutionResult.output` is copied directly from:

```text
StrategyOutcome.output
```

The execution layer does not inspect its semantic correctness.

For example:

```text
output = "refund"
```

does not imply:

```text
correct
incorrect
passed
failed
good
bad
```

Execution records the value.

Evaluation judges it.

# Metrics Are Recorded, Not Scored

If a strategy reports `StrategyExecutionMetrics`, those metrics are preserved
on the `ExecutionResult`.

```text
StrategyOutcome.metrics
        │
        ▼
ExecutionResult.metrics
```

Possible measurements include:

```text
provider

model

prompt tokens

completion tokens

total tokens

latency

estimated cost
```

The executor does not convert those measurements into:

```text
quality scores

cost scores

latency scores

rankings

optimization decisions
```

The distinction is:

```text
measurement
    ≠
judgment
```

# Initial Context

`ExecutionResult.initial_context` is the exact context supplied to
`StrategyExecutor.execute()`.

```text
caller Context
      │
      ▼
initial_context
```

It does not include the executor's start event unless that event was already
present before execution.

This gives the result an explicit before-state.

# Final Context

`ExecutionResult.final_context` contains the successful execution history after:

```text
start event

strategy-emitted events

completion event
```

have been appended.

```text
initial_context
      │
      ▼
+ execution events
      │
      ▼
final_context
```

Because `Context` is immutable, retaining both values does not create mutable
aliasing between before and after state.

# Context Transition as Evidence

Together:

```text
initial_context

final_context
```

show the state transition produced by execution.

Conceptually:

```text
ExecutionResult
       │
       ├── initial_context
       │
       └── final_context
```

A caller can compare the two to determine which events were introduced during
the successful execution lifecycle.

# Execution Does Not Mutate Shared Context

The executor repeatedly uses:

```text
Context.append()
```

which creates new immutable context values.

The original supplied context remains unchanged.

```text
Context A
   │
   ├─────────────── retained as initial_context
   │
   ▼
append lifecycle event
   │
   ▼
Context B
   │
   ▼
append strategy events
   │
   ▼
Context C
   │
   ▼
append completion event
   │
   ▼
Context D = final_context
```

This makes execution-state transitions explicit.

# Lifecycle Ordering

For a successful execution, ordering is guaranteed by construction.

```text
existing events

strategy.execution.started

strategy event 1

strategy event 2

...

strategy.execution.completed
```

The executor does not reconstruct this order from timestamps.

It constructs the immutable context in that order.

# Execution and Failure Propagation

V1 `StrategyExecutor` records the successful execution lifecycle.

It does **not** catch exceptions raised by:

```text
Strategy.run()
```

If a strategy raises:

```text
Strategy.run()
      │
      ▼
exception
      │
      ▼
propagates to caller
```

no `ExecutionResult` is returned by `StrategyExecutor`.

Likewise, because execution does not reach successful completion, the executor
does not append:

```text
strategy.execution.completed
```

to a returned final context.

This is an important V1 boundary.

# StrategyExecutor Does Not Manufacture Failure Evidence

The execution package contains no model equivalent to:

```text
FailedExecutionResult
```

and no generic failure repository.

Generic strategy exceptions propagate to the orchestration layer that invoked
the executor.

That means:

```text
strategy execution failure
       │
       ▼
higher-level orchestration
```

owns deciding what happens next.

# Failure Versus Workflow Failure

Workflows add richer failure semantics around strategy execution.

A workflow may own concepts such as:

```text
attempts

retries

step failures

failure policy

dependent-step behavior
```

Those concerns do not belong to `StrategyExecutor`.

Conceptually:

```text
StrategyExecutor
    attempt execution

WorkflowRunner
    orchestrate attempts and workflow policy
```

This allows the generic execution package to stay narrow.

# Execution Does Not Retry

`StrategyExecutor.execute()` performs one strategy execution attempt.

It does not internally retry a failing strategy.

```text
one call
    =
one execution attempt
```

Retry policy belongs to higher-level orchestration.

This distinction prevents hidden execution behavior from changing empirical
evidence.

# Execution Does Not Evaluate

Execution records:

```text
what strategy ran

what it returned

what events it produced

what metrics it measured

when execution began and completed
```

It does not determine whether the output satisfies an expected outcome.

```text
ExecutionResult
       │
       ▼
Evaluator
       │
       ▼
EvaluationResult
```

Therefore:

```text
execution
    ≠
evaluation
```

# Execution Does Not Score

Even when metrics contain cost or latency information, the execution package
does not normalize or score those values.

```text
ExecutionResult
    raw evidence

WorkflowScorecard / ranking logic
    interpretation
```

Execution remains empirical input rather than decision policy.

# Execution Does Not Optimize

The execution package does not compare candidates.

```text
ExecutionResult A
ExecutionResult B
ExecutionResult C
```

may later feed experimentation or optimization, but
`azathoth.execution` never decides:

```text
A is best

B should replace A

C should be promoted
```

Its responsibility ends at faithfully recording a successful execution.

# Execution Does Not Promote

An executable strategy successfully running does not grant production
authority.

```text
ExecutionResult
    evidence

WorkflowProductionState
    production execution authority
```

These concepts remain completely separate.

# Execution and Strategies

`azathoth.strategies` defines:

```text
Strategy

StrategyOutcome
```

`azathoth.execution` consumes those abstractions.

```text
Strategy
   │
   ▼
StrategyExecutor
   │
   ▼
ExecutionResult
```

Strategies focus on behavior.

The executor surrounds that behavior with standardized lifecycle evidence.

# Execution and Context

`azathoth.context` supplies the immutable state representation used throughout
execution.

```text
Context
   │
   ▼
StrategyExecutor
   │
   ▼
Context.append(...)
   │
   ▼
final Context
```

Execution does not introduce a separate mutable tracing state.

Lifecycle information becomes normal `ContextEvent` data.

# Execution and Prompting

Prompt-backed strategies satisfy the same `Strategy` contract.

```text
PromptStrategy
        │
        ▼
StrategyExecutor
        │
        ▼
ExecutionResult
```

Prompt-specific information such as provider/model identity and token usage
arrives through the strategy's provider-neutral metrics.

The execution layer does not call model providers directly.

# Execution and Tools

`ToolStrategy` also satisfies the common strategy contract.

```text
ToolStrategy
      │
      ▼
StrategyExecutor
      │
      ▼
ExecutionResult
```

The executor does not need a special generic tool-execution path.

Tool-specific runtime behavior remains inside the tool subsystem.

# Execution and Workflows

Workflows use strategy execution as a lower-level primitive.

Conceptually:

```text
WorkflowRunner
      │
      ▼
workflow step
      │
      ▼
StrategyExecutor
      │
      ▼
ExecutionResult
      │
      ▼
WorkflowStepRun
```

The workflow layer can then add:

```text
step identity

dependency topology

attempt history

retry behavior

failure behavior

workflow value propagation

workflow-level timing
```

without changing the generic execution contract.

# Execution Evidence Inside Workflow Evidence

An `ExecutionResult` may become part of a richer workflow record.

```text
ExecutionResult
      │
      ▼
WorkflowStepAttempt
      │
      ▼
WorkflowStepRun
      │
      ▼
WorkflowRun
```

The execution object remains the evidence for one successful strategy
execution.

The workflow record adds orchestration semantics around it.

# Execution and Evaluation

Evaluation consumes execution evidence.

```text
ExecutionResult.output
        │
        +
ExpectedOutcome
        │
        ▼
Evaluator
        │
        ▼
EvaluationResult
```

This allows the exact same execution to be judged under different evaluation
policies without rerouting execution behavior.

The execution layer therefore remains neutral.

# Execution and Optimization

Optimization builds on accumulated empirical evidence.

Conceptually:

```text
candidate
   │
   ▼
execute
   │
   ▼
ExecutionResult
   │
   ▼
evaluate
   │
   ▼
score / rank
   │
   ▼
optimization
```

Execution is one stage of that pipeline.

It does not own the stages after it.

# Execution Is Provider-Neutral

The executor depends on:

```text
Strategy

Context
```

not:

```text
OpenRouter

LanguageModel

ModelCatalog

ModelPortfolio

ToolImplementation

provider SDKs
```

Provider-backed behavior is hidden behind the strategy abstraction.

This lets deterministic, prompt-backed, and tool-backed strategies share the
same execution infrastructure.

# Execution Is Strategy-Agnostic

`StrategyExecutor` makes no type-specific branch such as:

```text
if PromptStrategy

if ToolStrategy

if EventFieldStrategy
```

The strategy protocol is sufficient.

That is the value of the strategy boundary:

```text
many behavior implementations
        │
        ▼
one execution lifecycle
```

# Execution Is Not Persistence

The V1 execution package defines no repository.

`ExecutionResult` is an immutable evidence object, but
`azathoth.execution` does not independently persist it.

Higher-level domains may persist artifacts containing execution evidence.

For example, workflow persistence may retain execution results inside durable
workflow runs.

Persistence belongs to the domain that owns the larger durable artifact.

# Execution Is Not Runtime Composition

`StrategyExecutor` executes an already constructed strategy.

It does not resolve:

```text
workflow specifications

models

model portfolios

language-model implementations

tool definitions

tool implementations
```

Those runtime composition concerns occur before execution.

```text
runtime composition
       │
       ▼
executable Strategy
       │
       ▼
StrategyExecutor
```

# Execution Is Not Workflow Orchestration

The execution package handles one strategy at a time.

It does not know:

```text
which workflow step owns the strategy

what steps depend on it

where its output should flow

whether a condition allows execution

whether failure should stop a workflow
```

Those semantics remain above this package.

# Successful Execution Evidence

For a successful strategy call, the complete V1 execution record is:

```text
                         BEFORE

                    initial_context
                           │
                           ▼

                 StrategyExecutor
                           │
                           ▼
             strategy.execution.started
                           │
                           ▼
                     Strategy.run()
                           │
                           ▼
                   StrategyOutcome
                   ├── output
                   ├── events
                   └── metrics
                           │
                           ▼
                 append outcome events
                           │
                           ▼
            strategy.execution.completed
                           │
                           ▼

                          AFTER

                     final_context
                           │
                           ▼

                    ExecutionResult
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
          behavior evidence      timing evidence
```

# V1 Execution Principles

The V1 execution architecture can be summarized as:

```text
behavior
    ≠
execution lifecycle

StrategyOutcome
    ≠
ExecutionResult

execution
    ≠
evaluation

measurement
    ≠
scoring

one execution attempt
    ≠
retry policy

strategy exception
    ≠
successful execution evidence

execution evidence
    ≠
production authority

execution
    ≠
persistence
```

The central rule is:

```text
Strategies behave.

Execution records.

Higher layers interpret.
```

That keeps Azathoth's empirical evidence trustworthy by preventing execution
infrastructure from quietly becoming evaluation, retry, optimization, or
deployment policy.