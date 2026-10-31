# Concepts

This page explains how Azathoth is put together, and why. To use it, start
with [Getting Started](getting-started.md). Come here when you want to know
what is behind the commands.

## Composition, Not Code

Most LLM workflows today are programs. A prompt is a string in a source
file, the model is a constant, and the control flow between steps is code.
So every change goes through engineering: trying another model, rewording a
prompt, adding a review step, routing one kind of request differently.

Azathoth moves workflow construction out of programming and into
composition. A workflow is a JSON document that composes:

- **steps**, which are prompts, tools or child workflows;
- **dependencies** between steps, and the values they pass along;
- **model requirements**, such as modalities, context window or price,
  rather than hard-coded models;
- **conditions**, **retries** and **failure policies**;
- a declared **result**.

Code still has a place, a precise one: **tools**. A tool is a small,
versioned, testable unit of deterministic work, such as counting, merging,
validating or calling an API. Engineers write tools. The workflows that use
them are assembled, reviewed, benchmarked and promoted by the people who own
the outcome:

- **platform and DevOps teams**, who run the workflows as infrastructure, with
  revisions, promotion, production state and an audit trail;
- **domain experts**, who know what a good answer looks like and say so in
  benchmarks.

Azathoth then finds the models that pass those benchmarks, at the latency and
cost the team targets. Deploying them stays a deliberate step.

```text
engineers ──► tools (code, tests)
                 │
                 ▼
platform & domain teams ──► workflows (composed documents)
                                 │
                                 ▼
                       benchmarks ──► optimize ──► promote ──► production
```

Writing code should be for tools, not for LLM workflows.

## Why Measure?

AI applications routinely make decisions such as:

- which model should handle a request;
- which prompt should be used;
- how context should be constructed;
- whether tools are required;
- how a task should be decomposed;
- what should happen when a step fails;
- which model substitutions remain legal;
- how candidate workflows compare;
- what should be promoted; and
- which workflow performs best under quality, reliability, latency, and cost constraints.

Those decisions are usually encoded manually or buried inside one mutable agent loop.

Azathoth treats them as explicit empirical and operational problems.

The framework separates durable intent, runtime composition, execution, evaluation, experimentation, optimization, and production authority so each layer can evolve independently while remaining reproducible, inspectable, and testable.

The important distinctions are:

```text
durable intent
    ≠
runtime implementation

execution
    ≠
evaluation

evaluation
    ≠
scoring

scoring
    ≠
optimization

optimization
    ≠
promotion

promotion
    ≠
production invocation

historical deployment
    ≠
current production authority
```

## Design Principles

Azathoth is built around a few core principles.

### Evidence over intuition

Optimization decisions should be backed by recorded execution and evaluation evidence.

A candidate is not better because an optimizer proposed it.

It must return through execution, evaluation, scoring, and empirical comparison.

### Immutable domain models

Important configuration, execution, evaluation, experiment, and audit artifacts are immutable so evidence remains reproducible and inspectable.

### Provider independence

Durable workflows describe model intent and requirements without persisting live provider clients.

Provider-specific implementations are attached during runtime composition.

### Explicit boundaries

Context, strategy behavior, execution, evaluation, scoring, ranking, experimentation, optimization, runtime composition, persistence, and production authority remain separate responsibilities.

### Deterministic infrastructure

The surrounding optimization substrate should remain deterministic wherever possible even when the models being evaluated are not.

### Replaceable optimization

Optimization policy remains separate from deterministic execution, evaluation, scoring, ranking, and experimentation.

Applications may provide their own optimization implementations through Azathoth's public optimization interfaces.

### Explicit production authority

Production does not mean:

```text
latest optimizer winner

latest configured workflow

latest historical revision

currently cheapest model
```

Production means:

```text
current WorkflowProductionState
```

Changes to that state happen through explicit promotion.

## Architecture

At the highest level:

```text
                              GOALS
                                │
                                ▼
                      durable objective intent
                                │

                         WORKFLOW DEFINITION
                                │
                                ▼
                      WorkflowSpecification
                                │
                                ▼

                         RUNTIME COMPOSITION
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
               models         tools        context
                  │             │             │
                  └─────────────┼─────────────┘
                                ▼
                       WorkflowCandidate
                                │
                                ▼

                            EXECUTION
                                │
                                ▼
                          WorkflowRun
                                │
                                ▼

                           EVALUATION
                                │
                                ▼
                       evaluation evidence
                                │
                                ▼

                    SCORING / EXPERIMENTATION
                                │
                                ▼
                       empirical evidence
                                │
                                ▼

                          OPTIMIZATION
                                │
                                ▼
                     candidate generation
                                │
                                ▼

                     EXPLICIT PRODUCTION
                                │
                   ┌────────────┴────────────┐
                   ▼                         ▼
       WorkflowProductionState   WorkflowProductionRevision
           execution authority         audit history
                   │
                   ▼
          ProductionInvocation
                   │
                   ▼
              WorkflowRun
```

The system deliberately separates:

```text
WorkflowSpecification
    durable orchestration intent

WorkflowCandidate
    executable realization

WorkflowRun
    empirical execution evidence

EvaluationResult
    judgment

WorkflowOptimizationSession
    empirical search

WorkflowProductionState
    current production authority

WorkflowProductionRevision
    deployment audit history

ProductionInvocation
    external production call
```

Each artifact is allowed to mean one thing.

## The Core Lifecycle

### 1. Define

A `WorkflowSpecification` describes durable workflow intent.

```text
WorkflowSpecification
├── metadata
└── steps
    ├── prompt-backed behavior
    ├── tool-backed behavior
    ├── dependencies
    ├── inputs
    ├── outputs
    ├── conditions
    ├── retry policy
    └── failure policy
```

The specification does not persist live provider clients or runtime implementations.

### 2. Generate

Runtime composition turns durable intent into an executable `WorkflowCandidate`.

```text
WorkflowSpecification
        │
        +
current ModelCatalog
        │
        +
authorized ModelPortfolio
        │
        +
LanguageModelRegistry
        │
        +
tool catalogs
        │
        ▼
WorkflowCandidate
```

This is where durable requirements meet what the current process can actually execute.

### 3. Execute

`WorkflowRunner` executes the candidate and records a `WorkflowRun`.

```text
WorkflowCandidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

Execution records what happened.

It does not decide whether the result was correct.

### 4. Evaluate

Expected outcomes and evaluators judge observed results.

```text
ExpectedOutcome
       +
actual output
       │
       ▼
Evaluator
       │
       ▼
EvaluationResult
```

Evaluation is independent from execution.

### 5. Experiment

Workflow experiments compose execution, evaluation, scoring, and ranking.

```text
Workflow Candidates
        │
        ▼
WorkflowExperimentRunner
        │
        ├── execute
        ├── evaluate
        ├── score
        └── rank
        │
        ▼
WorkflowExperimentResult
```

Experiments produce empirical evidence about a candidate population.

They do not generate new candidates.

### 6. Optimize

Optimization consumes experiment evidence and proposes a next population.

```text
WorkflowExperimentResult
          +
Current Candidates
          │
          ▼
   WorkflowOptimizer
          │
          ▼
WorkflowOptimizationResult
```

Azathoth includes:

```text
ReplayWorkflowOptimizer

ModelSubstitutionWorkflowOptimizer
```

Model substitution can explore strictly cheaper legal model bindings.

A cheaper candidate is not automatically trusted.

It must be executed and evaluated empirically.

The optimization report names the winner of each generation and of the final
evaluation, and the model each of its prompt steps ran on. The final
evaluation's winner, or the last generation's when no final evaluation was
needed, is the session's winner. To deploy the winner, promote it by its experiment
ID: promotion rebuilds it from the workflow's current revision and pins each
prompt step to the model it was measured on (ADR 0092). To make those models
part of the workflow itself, pin them as fixed selections in a new revision.
A fixed selection is never substituted, so a pinned step stays exactly as
measured.

### 7. Promote

Production changes are explicit.

```text
WorkflowCandidate
        │
        ▼
explicit promotion
        │
        ├── WorkflowProductionState
        └── WorkflowProductionRevision
```

`WorkflowProductionState` is the current durable production execution authority.

`WorkflowProductionRevision` is immutable deployment history.

A revision is not an active pointer.

### 8. Invoke

External production calls execute active production state.

```text
ProductionInvocation
        │
        ▼
WorkflowProductionState
        │
        ▼
production execution
        │
        ▼
WorkflowRun
        │
        ▼
ProductionInvocationResult
```

The invocation is durably associated with the run it produced.

## Core Concepts

### Context

`Context` is an immutable ordered history of `ContextEvent` objects.

```python
from azathoth.context import Context, ContextEvent

context = Context()

context = context.append(
    ContextEvent(
        event_type="request.received",
        payload={
            "text": "What is the answer?",
        },
        producer="example",
    )
)
```

Appending information returns a new context rather than mutating shared state.

See [`azathoth.context`](../src/azathoth/context/README.md).

### Goals

`Goal` defines stable objective intent.

```text
Goal
├── name
├── description
├── success criteria
└── constraints
```

Goals describe what should be achieved.

They do not contain executable strategy, evaluator, workflow, model, or optimizer policy.

See [`azathoth.goals`](../src/azathoth/goals/README.md).

### Strategies

A strategy is an executable operation with stable metadata.

```text
Context
   │
   ▼
Strategy
   │
   ▼
StrategyOutcome
```

Strategies own behavior.

They do not own workflow orchestration, retries, evaluation, ranking, or production deployment.

See [`azathoth.strategies`](../src/azathoth/strategies/README.md).

### Execution

`StrategyExecutor` records successful strategy execution.

```text
Strategy
   │
   ▼
StrategyExecutor
   │
   ▼
ExecutionResult
```

Execution results record strategy identity, output, metrics, context transition, and timing.

Execution says what happened.

See [`azathoth.execution`](../src/azathoth/execution/README.md).

### Evaluation

Evaluation compares an actual result with an expected outcome.

```text
ExpectedOutcome
       +
Actual Result
       │
       ▼
Evaluator
       │
       ▼
EvaluationResult
```

Evaluation says how well an observed output satisfied an expectation.

It remains separate from workflow scoring.

See [`azathoth.evaluation`](../src/azathoth/evaluation/README.md).

## Prompting and Models

Prompt-backed steps separate durable intent from executable provider behavior.

```text
PromptStrategySpec
        │
        ▼
model selection
        │
        ▼
candidate generation
        │
        ▼
PromptStrategy
```

Configured prompt steps may use:

```text
PortfolioModelSelection

FixedModelSelection
```

Portfolio selection allows Azathoth to choose among authorized, current, executable models satisfying the declared requirements.

Fixed selection means exactly the requested provider/model identity.

Fixed intent does not silently fall back to the portfolio.

See [`azathoth.prompting`](../src/azathoth/prompting/README.md).

## Providers

The provider architecture distinguishes current provider truth, historical observation, organizational authorization, metadata, and executable implementations.

```text
ProviderModel
    current provider truth

ProviderModelObservation
    historical provider evidence

ModelCatalog
    current normalized metadata

ModelPortfolio
    organizational authorization

LanguageModelRegistry
    executable implementations
```

Therefore:

```text
history
    ≠
current state

availability
    ≠
authorization

metadata
    ≠
executability
```

Azathoth 1.0 includes OpenRouter provider discovery and execution behind provider-neutral interfaces.

See [`azathoth.providers`](../src/azathoth/providers/README.md).

## Heterogeneous Model Execution

Model-backed workflow steps do not share one required global model.

```text
Workflow
│
├── Step A
│   └── model selection A
│
├── Step B
│   └── model selection B
│
└── Step C
    └── model selection C
```

Candidate generation resolves each prompt-backed step independently.

This allows one workflow to use different models for different responsibilities.

## Tools

The tools package separates capability contracts from executable implementations.

```text
ToolRequirement
       │
       ▼
ToolDefinition
       │
       ▼
ToolImplementation
       │
       ▼
ToolExecutor
       │
       ▼
ToolStrategy
```

Capability resolution determines what capability satisfies a requirement.

Implementation resolution determines how that capability can execute.

The subsystem also supports durable tool test cases and deterministic verification.

See [`azathoth.tools`](../src/azathoth/tools/README.md).

## Tool-Backed Workflows

Durable tools can execute as ordinary workflow steps.

```text
ToolRequirement
      │
      ▼
ToolDefinition
      │
      ▼
resolved ToolImplementation
      │
      ▼
ToolStrategy
      │
      ▼
WorkflowValue
```

Tool-backed steps participate in the same dependency, value-binding, retry, failure, and conditional-execution infrastructure as prompt-backed steps.

## Workflows

A workflow specification describes a dependency graph without embedding executable runtime instances.

```text
WorkflowSpecification
        │
        ▼
candidate generation
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

Workflow steps can declare:

- dependencies;
- input bindings;
- exported values;
- conditions;
- retry policies; and
- failure policies.

Execution proceeds in dependency-safe layers while preserving deterministic evidence ordering.

See [`azathoth.workflows`](../src/azathoth/workflows/README.md).

## Values, Prompts and Replies

Steps pass values by name. A step declares the outputs it produces, and later
steps bind them as inputs. Prompt templates can use those inputs directly:

```json
{"variable_name": "plan", "input_name": "plan"}
```

Structured values reach the model as JSON (ADR 0087).

A prompt step can declare that its reply is JSON:

```json
"output_format": "json"
```

The reply is then parsed before later steps read it, so a step can use one
field of it, such as a plan's chapters or a ticket's category (ADR 0088).

A value can also be referenced by name alone. The first step, in declared
order, that actually produced it supplies it. That is how a primary and a
fallback, or one of several conditional branches, feed the same consumer
(ADR 0080).

## Child Workflows and Loops

A workflow is a directed acyclic graph: each step runs at most once per run.
Larger behavior is built by composing workflows, not by adding control flow:

- **child workflows**: the `run_workflow` tool invokes another workflow's
  production state and returns its result (ADR 0084);
- **loops**: the `loop_workflow` tool invokes a child once per iteration and
  carries plain JSON state between iterations, until the child says it is
  done or a limit is reached (ADR 0090).

Every child invocation is a production invocation with its own run, so each
piece can be inspected, benchmarked, optimized and promoted on its own. Loops
are bounded by an iteration limit, a time budget and an 8-level depth limit.

There is no loop construct in the engine. Keeping the graph acyclic keeps
run records, conditions, benchmarks and optimization simple, and repetition
lives in a tool.

## Benchmarks and Judges

A benchmark case pairs an input with an expected outcome and a comparison:

- **exact**: the result must equal the expected value;
- **normalized**: equal after ignoring letter case and surrounding
  whitespace;
- **schema**: the result must validate against a JSON Schema;
- **semantic**: a language-model judge decides whether the result meets a
  described expectation.

Judges form a durable rotation of authorized models. Each semantic case is
always assigned the same first judge, so candidates are compared like with
like. Judge cost is recorded as Azathoth's own, never as the workflow's.

Benchmarks grow from use. A run marked bad, with its corrected output, becomes
a new case through `benchmark add-case --from-run`.

## Durable Execution Evidence

Completed workflow runs are durable evidence.

```text
WorkflowRun
    │
    ├── step execution results
    ├── attempts
    ├── failures
    ├── values
    ├── contexts
    └── timing
```

Later judgments remain separate artifacts.

```text
                    WorkflowRun
                    /         \
                   ▼           ▼
          Run Evaluation    Run Feedback
          machine judgment  human/app judgment
```

Recording later feedback or evaluation does not mutate the original execution evidence.

## Workflow Benchmarks

Azathoth can execute reusable benchmark datasets against workflow candidates.

```text
BenchmarkDataset
        │
        ▼
Workflow Candidates
        │
        ▼
Execution
        │
        ▼
Evaluation
        │
        ▼
Workflow Scorecards
        │
        ▼
Ranking
```

Benchmark datasets preserve versioned reusable workloads consisting of inputs, expected outcomes, case identity, and metadata.

See [`azathoth.evaluation`](../src/azathoth/evaluation/README.md).

## Workflow Experiments

Workflow experiments record empirical comparisons between candidate workflows.

```text
candidate executions
        +
evaluations
        │
        ▼
scorecards
        │
        ▼
ranking
        │
        ▼
WorkflowExperimentResult
```

Experiments produce evidence.

They do not mutate candidate definitions or choose what production executes.

## Empirical Workflow Optimization

Azathoth includes a model-substitution optimizer capable of exploring strictly cheaper legal model bindings.

```text
empirical winner
      │
      ▼
cheaper legal substitutions
      │
      ▼
execute
      │
      ▼
evaluate
      │
      ▼
score
      │
      ▼
rank
```

The optimizer does not declare its proposals better.

Existing experiment infrastructure must prove that empirically.

Optimization policy remains replaceable through the `WorkflowOptimizer` protocol.

See [`azathoth.optimization`](../src/azathoth/optimization/README.md).

## Runtime Composition

Durable configuration and process-local implementations are composed through `AzathothRuntime`.

```text
reconstructed catalogs
        +
current provider state
        +
runtime implementations
        │
        ▼
AzathothRuntime
        │
        ▼
workflow ID
        │
        ▼
WorkflowCandidate
```

The runtime does not own persistence.

It does not execute workflows.

It provides one immutable process-local composition snapshot for turning configured workflow identities into executable candidates.

See [`azathoth.runtime`](../src/azathoth/runtime/README.md).

## Production

Azathoth's production model is deliberately explicit.

### Production State

`WorkflowProductionState` records current intended production behavior.

For prompt-backed production steps:

```text
fixed primary model
        │
        ├── available ──► execute
        │
        ▼
ordered explicit substitutes
        │
        ├── available ──► execute
        │
        ▼
explicit failure
```

Production does not silently return to portfolio selection.

### Production Revisions

Promotion also records immutable deployment history:

```text
WorkflowProductionRevision
```

But:

```text
WorkflowProductionRevision
    ≠
execution authority
```

Revisions are the audit log of deployments.

`WorkflowProductionState` is what production executes.

### Production Invocations

Production calls are represented by durable `ProductionInvocation` objects.

```text
ProductionInvocation
        │
        ▼
WorkflowProductionState
        │
        ▼
WorkflowRun
```

Azathoth records the durable relationship between the external invocation and the run it produced.

## Package Guide

Detailed architecture lives with each major package.

| Package | Responsibility |
| --- | --- |
| [`azathoth.cli`](../src/azathoth/cli/README.md) | Installed operator surface and runtime bootstrap |
| [`azathoth.context`](../src/azathoth/context/README.md) | Immutable event-backed working context |
| [`azathoth.goals`](../src/azathoth/goals/README.md) | Durable objective intent |
| [`azathoth.strategies`](../src/azathoth/strategies/README.md) | Executable strategy contracts and outcomes |
| [`azathoth.execution`](../src/azathoth/execution/README.md) | Strategy execution evidence |
| [`azathoth.evaluation`](../src/azathoth/evaluation/README.md) | Expected outcomes, evaluators, evidence, and benchmarks |
| [`azathoth.prompting`](../src/azathoth/prompting/README.md) | Prompt specifications, bindings, model selection, and executable prompt strategies |
| [`azathoth.providers`](../src/azathoth/providers/README.md) | Provider truth, model metadata, authorization, discovery, and executable registries |
| [`azathoth.tools`](../src/azathoth/tools/README.md) | Durable tool capabilities, implementations, execution, and verification |
| [`azathoth.workflows`](../src/azathoth/workflows/README.md) | Workflow definition, execution, evidence, experiments, and production |
| [`azathoth.optimization`](../src/azathoth/optimization/README.md) | Empirical candidate generation and optimization |
| [`azathoth.runtime`](../src/azathoth/runtime/README.md) | Process-local executable composition |

Architectural decisions are recorded under [`docs/adrs`](adrs/README.md).
