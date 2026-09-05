# Strategies

`azathoth.strategies` defines Azathoth's common executable strategy contract.

A strategy consumes immutable execution `Context` and asynchronously produces a
`StrategyOutcome`.

```text
Context
   │
   ▼
Strategy
   │
   ▼
StrategyOutcome
   ├── output
   ├── events
   └── metrics
```

This boundary allows execution infrastructure to run different kinds of
behavior through the same interface without knowing how that behavior is
implemented.

## Architectural Role

Strategies are executable behavior.

They sit between structured execution state and execution infrastructure.

```text
Context
   │
   ▼
executable behavior
   │
   ▼
StrategyOutcome
```

The strategy package defines:

- the `Strategy` protocol;
- stable strategy metadata;
- the direct result of strategy execution;
- provider-neutral execution metrics;
- common strategy execution failures; and
- a deterministic reference implementation, `EventFieldStrategy`.

It does not define:

- execution orchestration;
- workflow topology;
- retry policy;
- evaluation;
- scoring;
- ranking;
- optimization;
- provider discovery;
- model authorization; or
- production deployment.

The central distinction is:

```text
Strategy
    describes executable behavior

execution infrastructure
    records and orchestrates that behavior
```

# Public Surface

The V1 package exports:

```python
from azathoth.strategies import (
    EventFieldStrategy,
    RequiredEventNotFoundError,
    RequiredFieldNotFoundError,
    Strategy,
    StrategyError,
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)
```

This deliberately small surface establishes the common execution vocabulary
used by higher-level Azathoth systems.

# Strategy Protocol

`Strategy` is a structural protocol.

A strategy must expose:

```text
metadata

async run(context)
```

Conceptually:

```python
class Strategy(Protocol):
    @property
    def metadata(self) -> StrategyMetadata: ...

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome: ...
```

The protocol says nothing about the internal implementation.

A strategy may be backed by deterministic Python behavior, a language model, or
another implementation that satisfies the same contract.

The protocol boundary remains:

```text
Context
   │
   ▼
Strategy.run()
   │
   ▼
StrategyOutcome
```

# Asynchronous Execution Contract

`Strategy.run()` is asynchronous.

```python
outcome = await strategy.run(context)
```

The protocol therefore supports implementations whose work may involve
asynchronous resources without requiring execution infrastructure to know which
strategies actually perform external I/O.

The asynchronous contract belongs to the strategy interface.

Scheduling, retries, workflow dependencies, and lifecycle recording remain
outside it.

# Context In

Every strategy receives an immutable `Context`.

```text
Strategy.run(
    context
)
```

The strategy can inspect context using the context domain's explicit event
history.

It does not receive a mutable application-state dictionary.

```text
Context
    ordered immutable history

Strategy
    consumer of that history
```

This makes strategy behavior compatible with Azathoth's event-backed execution
state.

# StrategyOutcome Out

Every successful strategy execution returns a `StrategyOutcome`.

```text
StrategyOutcome
├── output
├── events
└── metrics
```

The model is immutable.

These fields represent the direct result produced by the strategy itself.

They are not yet a complete execution record.

That distinction is important:

```text
StrategyOutcome
    direct strategy result

ExecutionResult
    execution infrastructure's recorded lifecycle evidence
```

# Output

`StrategyOutcome.output` is a JSON-compatible value.

```python
StrategyOutcome(
    output="success",
)
```

The output may therefore be represented as structured data without passing
arbitrary executable Python objects across the strategy boundary.

Conceptually:

```text
arbitrary live Python object
           ✗

JSON-compatible result
           ✓
```

This keeps strategy results compatible with the broader durable-evidence
architecture.

# Emitted Context Events

A strategy may return additional `ContextEvent` objects.

```python
StrategyOutcome(
    output="duplicate_charge",
    events=(event,),
)
```

These events describe information produced by the strategy.

```text
Strategy
   │
   ▼
StrategyOutcome
   │
   └── ContextEvent(s)
```

The strategy does not need to mutate the supplied `Context`.

Instead:

```text
input Context
     │
     ▼
Strategy
     │
     ▼
emitted events
     │
     ▼
execution infrastructure
     │
     ▼
new recorded Context
```

This preserves the immutable context boundary.

# StrategyExecutionMetrics

A strategy may include optional `StrategyExecutionMetrics`.

The model is provider-neutral and immutable.

V1 fields are:

```text
provider

model

prompt_tokens

completion_tokens

total_tokens

latency_ms

estimated_cost_usd
```

Every field is optional.

Conceptually:

```text
StrategyExecutionMetrics
├── provider: optional
├── model: optional
├── prompt_tokens: optional
├── completion_tokens: optional
├── total_tokens: optional
├── latency_ms: optional
└── estimated_cost_usd: optional
```

This allows strategies that do not use language models to participate in the
same contract without manufacturing irrelevant provider data.

# Metric Validation

Numeric execution metrics cannot be negative.

This applies to:

```text
prompt_tokens >= 0

completion_tokens >= 0

total_tokens >= 0

latency_ms >= 0

estimated_cost_usd >= 0
```

When all three token counts are supplied, Azathoth also requires:

```text
total_tokens
    =
prompt_tokens + completion_tokens
```

Inconsistent token evidence is rejected instead of being silently retained.

# Metrics Are Measurements, Not Judgments

`StrategyExecutionMetrics` records measurements.

It does not interpret them.

```text
latency_ms = 250
estimated_cost_usd = 0.001
```

does not itself imply:

```text
good
bad
fast enough
too expensive
preferred
winner
```

Those judgments belong to evaluation, scoring, ranking, and optimization
layers.

The distinction is:

```text
measurement
    ≠
evaluation
```

# StrategyMetadata

Every strategy exposes `StrategyMetadata`.

The immutable model contains:

```text
id

name

description

version
```

Example:

```python
from azathoth.strategies import StrategyMetadata

metadata = StrategyMetadata(
    name="Extract customer message",
    description="Extract the latest customer message from context.",
)
```

If no ID is supplied, one is generated.

If no version is supplied, V1 defaults to:

```text
1.0.0
```

# Strategy Identity

Strategy identity is explicit.

```text
StrategyMetadata.id
```

is distinct from:

```text
name

description

version
```

Higher-level systems can therefore carry strategy identity through execution
and empirical evidence without relying on display names as identifiers.

Prompt candidate generation can also derive deterministic strategy identities
from durable specification identity and model identity.

The strategy package merely provides the metadata representation used for that
identity.

# Metadata Is Not Behavior

`StrategyMetadata` describes an executable strategy.

It does not implement it.

```text
StrategyMetadata
      ≠
Strategy
```

Likewise:

```text
same descriptive role
      ≠
same strategy identity
```

Identity and executable behavior remain explicit.

# StrategyOutcome Versus ExecutionResult

A strategy returns `StrategyOutcome`.

Higher-level execution infrastructure produces `ExecutionResult`.

The lifecycle is:

```text
Context
   │
   ▼
StrategyExecutor
   │
   ▼
Strategy.run()
   │
   ▼
StrategyOutcome
   │
   ▼
StrategyExecutor
   │
   ▼
ExecutionResult
```

`StrategyOutcome` contains what the strategy directly produced.

`ExecutionResult` adds execution infrastructure concerns such as:

```text
strategy identity

initial context

final context

started_at

completed_at
```

The strategy package does not create that complete lifecycle record itself.

# Strategies Do Not Own Context Mutation

A strategy receives a `Context`.

It may emit `ContextEvent` objects.

It does not need to return a replacement `Context`.

```text
Strategy
   │
   ├── reads Context
   │
   └── emits ContextEvent(s)
```

Execution infrastructure owns the act of appending those events to recorded
execution context.

This keeps strategy implementations independent from context-history
orchestration.

# EventFieldStrategy

`EventFieldStrategy` is V1's deterministic strategy implementation.

It extracts one field from the latest context event of a configured type.

Its immutable configuration contains:

```text
metadata

event_type

field_name

output_event_type
```

where `output_event_type` is optional.

Conceptually:

```text
Context
   │
   ▼
latest(event_type)
   │
   ▼
ContextEvent
   │
   ▼
payload[field_name]
   │
   ▼
StrategyOutcome.output
```

# Latest-Event Resolution

`EventFieldStrategy` uses:

```text
Context.latest(event_type)
```

rather than scanning for arbitrary matching state.

Given:

```text
customer.message.received = "first"

customer.message.received = "second"
```

the strategy resolves:

```text
"second"
```

because it uses the latest matching context event.

This demonstrates how executable strategies consume Azathoth's ordered
event-backed context deterministically.

# EventFieldStrategy Output

If the configured event exists and contains the requested field, that field's
value becomes the strategy output.

```text
ContextEvent.payload[field_name]
            │
            ▼
StrategyOutcome.output
```

No provider, model, tool, or external service is required.

This makes `EventFieldStrategy` useful as a deterministic implementation for
exercising the common strategy architecture.

# Optional Derived Event

If `output_event_type` is configured, `EventFieldStrategy` also emits a derived
`ContextEvent`.

Conceptually:

```text
source ContextEvent
        │
        ▼
extract field
        │
        ├──────────────► StrategyOutcome.output
        │
        ▼
derived ContextEvent
        │
        ▼
StrategyOutcome.events
```

The derived event records:

```text
value

source_event_id

source_event_type

source_field
```

It also records:

```text
producer = strategy metadata ID

provenance = source event ID

confidence = source event confidence
```

This demonstrates a complete traceable context transformation without mutating
the original context.

# Provenance Through Strategy Execution

For a derived event:

```text
source event
    │
    ▼
EventFieldStrategy
    │
    ▼
derived event
```

V1 preserves the relationship through both:

```text
payload["source_event_id"]

provenance
```

and propagates the source event's confidence.

This provides explicit lineage for the new information generated by the
strategy.

# Strategy Failures

Strategy-specific execution failures derive from:

```text
StrategyError
```

V1 defines:

```text
RequiredEventNotFoundError

RequiredFieldNotFoundError
```

# Missing Event Failure

If `EventFieldStrategy` cannot find the configured event type:

```text
Context.latest(event_type)
        │
        ▼
None
        │
        ▼
RequiredEventNotFoundError
```

The strategy fails explicitly.

It does not return `None` as a successful result or manufacture a replacement
value.

# Missing Field Failure

If the required event exists but its payload lacks the configured field:

```text
ContextEvent
     │
     ▼
payload lacks field_name
     │
     ▼
RequiredFieldNotFoundError
```

Again, the failure is explicit.

# Failure Versus Retry

A strategy may raise a strategy execution error.

It does not decide whether that failure should be retried.

```text
Strategy
   │
   ▼
failure
```

versus:

```text
Workflow retry policy
    decides what happens next
```

This separation prevents executable strategy implementations from embedding
workflow orchestration policy.

# Strategies and Execution

`azathoth.execution` owns generic execution orchestration around a strategy.

Conceptually:

```text
Context
   │
   ▼
StrategyExecutor
   │
   ├── record execution start
   │
   ▼
Strategy.run()
   │
   ▼
StrategyOutcome
   │
   ├── append emitted events
   │
   ├── record completion
   │
   ▼
ExecutionResult
```

The strategy package defines the executable contract consumed by that
infrastructure.

It does not implement `StrategyExecutor`.

# Strategies and Prompting

`azathoth.prompting` provides language-model-backed implementations compatible
with `Strategy`.

```text
Strategy
   ▲
   │
PromptStrategy
ContextPromptStrategy
```

Those implementations may:

```text
render prompts

call LanguageModel.complete()

validate model bindings

produce model execution metrics
```

but execution infrastructure can still treat them through the same:

```text
Context -> StrategyOutcome
```

contract.

# Strategies and Providers

The `Strategy` protocol itself has no provider dependency.

```text
Strategy
    ≠
LanguageModel
```

Provider-backed strategies may internally use provider abstractions, but the
common strategy interface remains provider-neutral.

Likewise, provider/model fields in `StrategyExecutionMetrics` are optional.

This prevents the generic strategy domain from assuming that every executable
operation is an LLM call.

# Strategies and Tools

Tool-backed workflow behavior does not require the generic `Strategy` protocol
to understand durable tool definitions, implementations, or resolution.

Tool architecture owns those concepts.

The strategy boundary remains intentionally narrower:

```text
Context
   │
   ▼
executable behavior
   │
   ▼
StrategyOutcome
```

Where tool execution participates in higher-level workflow execution, the
workflow and tool domains own the additional semantics.

# Strategies and Workflows

Workflows compose executable behavior into a larger dependency-driven
operation.

```text
WorkflowCandidate
    │
    ├── executable step
    ├── executable step
    └── executable step
```

For strategy-backed behavior, the workflow layer can rely on the shared
strategy contract rather than knowing the implementation details.

The workflow domain owns:

```text
step topology

dependencies

input/output routing

conditions

retry policy

failure policy

workflow execution history
```

Strategies do not.

# Strategies and Evaluation

A `StrategyOutcome` records what happened.

It does not determine whether that result satisfies an expected outcome.

```text
StrategyOutcome
      │
      ▼
evaluation
      │
      ▼
judgment
```

Therefore:

```text
strategy execution
    ≠
evaluation
```

A strategy should not mark its own output as empirically superior.

# Strategies and Optimization

Optimization can compare strategies using execution and evaluation evidence.

```text
Strategy A ──► execute ──► evaluate ──┐
                                     │
Strategy B ──► execute ──► evaluate ──┼──► compare
                                     │
Strategy C ──► execute ──► evaluate ──┘
```

The strategy package supplies executable candidates and identifying metadata.

It does not:

```text
rank strategies

choose winners

generate optimization policy

promote production behavior
```

Those responsibilities belong elsewhere.

# Strategies and Goals

Goals and strategies represent different concepts.

```text
Goal
    desired objective

Strategy
    executable behavior
```

A goal can be used when constructing an experiment or optimization example.

A strategy can then be executed and evaluated against that objective.

The strategy package itself does not interpret goals or decide whether one has
been achieved.

# Direct Outcome Versus Durable Evidence

`StrategyOutcome` is an immutable domain value, but it is not by itself the
complete durable evidence record used by higher-level execution.

The distinction is:

```text
StrategyOutcome
    direct result returned by behavior

ExecutionResult
    recorded strategy execution

WorkflowRun
    recorded workflow execution

experiment evidence
    empirical comparison material
```

Higher layers progressively add context and meaning around the strategy's
direct result.

# Strategies Are Not Persistence

The V1 strategy package defines no repository.

It does not persist:

```text
StrategyMetadata

StrategyOutcome

StrategyExecutionMetrics

EventFieldStrategy
```

as an independent storage subsystem.

Higher-level artifacts may retain strategy metadata, outcomes, or metrics as
part of their own durable evidence.

Persistence belongs to the domain owning that durable artifact.

# Strategies Are Not Workflow Specifications

An executable `Strategy` is not the same thing as durable workflow intent.

```text
WorkflowSpecification
    durable orchestration intent

Strategy
    executable behavior
```

For example, prompting deliberately distinguishes:

```text
PromptStrategySpec
    durable specification

PromptStrategy
    executable strategy
```

That distinction prevents runtime implementations from leaking into durable
workflow configuration.

# Strategies Are Not Production Authority

A strategy can execute.

That does not make it production authority.

```text
Strategy
    executable behavior

WorkflowProductionState
    current durable production execution authority
```

Production state determines which workflow behavior production should invoke.

Strategy objects participate in executable runtime realizations of that intent.

They do not determine deployment state.

# Extension Boundary

The `Strategy` protocol intentionally requires only:

```text
metadata

async run(Context) -> StrategyOutcome
```

A compatible implementation therefore does not need to inherit from a common
base class.

It needs to satisfy the execution contract.

This keeps the abstraction structural and implementation-independent.

The package does not impose provider, prompt, workflow, or optimization
semantics on new strategy implementations.

# Complete V1 Strategy Boundary

```text
                         INPUT

                        Context
                           │
                           ▼

                     Strategy Protocol
                    ┌───────────────┐
                    │ metadata      │
                    │ async run()   │
                    └───────────────┘
                           │
                           ▼

                    StrategyOutcome
                    ┌───────────────┐
                    │ output        │
                    │ events        │
                    │ metrics       │
                    └───────────────┘
                           │
                           ▼

                  execution infrastructure
                           │
                           ▼

                    ExecutionResult
                           │
                           ▼

                 evaluation / workflows /
                  experiments / optimization
```

The strategy abstraction ends at `StrategyOutcome`.

Everything after that belongs to higher-level architecture.

# V1 Strategy Principles

The V1 strategy architecture can be summarized as:

```text
behavior
    ≠
orchestration

outcome
    ≠
execution record

measurement
    ≠
evaluation

failure
    ≠
retry policy

strategy
    ≠
workflow specification

strategy
    ≠
production authority
```

The core contract is deliberately simple:

```text
immutable structured context
        │
        ▼
executable behavior
        │
        ▼
structured immutable outcome
```

That gives Azathoth a common executable boundary without forcing prompt,
provider, workflow, evaluation, or optimization concerns into the strategy
domain.