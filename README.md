# Azathoth

> Empirical optimization for context-aware AI workflows.

Azathoth is an open-source Python framework for building AI systems that improve through measured evidence rather than intuition.

Instead of asking:

> Which prompt or model seems best?

Azathoth asks:

> Given this problem, which combination of workflow, strategy, prompt, model, tool, and execution policy consistently produces the best result?

Azathoth provides infrastructure for defining, executing, evaluating, experimenting with, optimizing, and operating production AI workflows while keeping each architectural responsibility explicit.

A workflow in Azathoth is durable intent.

Its executable realization is generated from current runtime capabilities.

Its behavior becomes evidence.

That evidence can be evaluated, scored, ranked, and optimized.

Moving new behavior into production is a separate explicit operation.

```text
define
  │
  ▼
generate
  │
  ▼
execute
  │
  ▼
evaluate
  │
  ▼
experiment
  │
  ▼
optimize
  │
  ▼
promote
  │
  ▼
invoke production
```

Azathoth is built around one core rule:

> **Persist what should happen. Compose what can execute. Record what actually happened. Change production deliberately.**

## Why Azathoth?

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

## Who Is This For?

Azathoth is for people building AI systems who want to replace hand-tuned intuition with empirical evidence.

It is particularly relevant for:

- **AI and LLM engineers** comparing prompts, models, providers, tools, and execution strategies;
- **agent and workflow developers** building multi-step systems that need measurable reliability;
- **researchers** experimenting with automated optimization, evaluation, and adaptive AI systems;
- **platform engineers** building provider-independent infrastructure for model selection and execution; and
- **developers exploring self-improving systems** where candidate solutions are generated, tested, measured, and iteratively improved.

Azathoth does not prescribe a single model, provider, prompting technique, workflow architecture, or optimization algorithm.

Instead, it provides the infrastructure to ask a more useful question:

> Given the evidence, what actually works best?

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

## Current Capabilities

Azathoth OSS V1 includes infrastructure for:

- immutable event-backed execution context;
- durable goals and expected outcomes;
- executable strategy protocols;
- deterministic strategy execution;
- provider-neutral model metadata and requirements;
- current provider model discovery;
- historical provider observations;
- organizational model authorization;
- fixed and portfolio-based model selection;
- model catalogs and executable model registries;
- OpenRouter model discovery and execution;
- prompt-backed strategies;
- deterministic prompt candidate generation;
- prompt templates and context bindings;
- model binding validation;
- durable tool capabilities;
- durable tool implementations;
- deterministic tool resolution;
- trusted Python tool execution;
- durable tool verification cases;
- workflow specifications;
- dependency-graph validation;
- dependency-layer execution;
- workflow value export and downstream binding;
- conditional workflow execution;
- retry policies;
- workflow failure policies;
- durable step-attempt history;
- durable workflow-run evidence;
- execution statistics;
- normalized reliability metrics;
- expected-outcome evaluation;
- deterministic exact-match evaluation;
- reusable benchmark datasets;
- deterministic workflow scoring;
- workflow scorecards;
- deterministic workflow ranking;
- durable workflow experiments;
- workflow optimization protocols;
- replay optimization;
- empirical cheaper-model substitution;
- multi-generation optimization sessions;
- explicit workflow promotion;
- durable production state;
- durable production revisions;
- ordered production model substitutions;
- durable production invocations;
- production workflow execution; and
- an installed CLI spanning configuration, execution, optimization, promotion, and production invocation.

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

OSS V1 includes:

```text
ReplayWorkflowOptimizer

ModelSubstitutionWorkflowOptimizer
```

Model substitution can explore strictly cheaper legal model bindings.

A cheaper candidate is not automatically trusted.

It must be executed and evaluated empirically.

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

See [`azathoth.context`](src/azathoth/context/README.md).

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

See [`azathoth.goals`](src/azathoth/goals/README.md).

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

See [`azathoth.strategies`](src/azathoth/strategies/README.md).

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

See [`azathoth.execution`](src/azathoth/execution/README.md).

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

See [`azathoth.evaluation`](src/azathoth/evaluation/README.md).

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

See [`azathoth.prompting`](src/azathoth/prompting/README.md).

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

OSS V1 includes OpenRouter provider discovery and execution behind provider-neutral interfaces.

See [`azathoth.providers`](src/azathoth/providers/README.md).

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

See [`azathoth.tools`](src/azathoth/tools/README.md).

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

See [`azathoth.workflows`](src/azathoth/workflows/README.md).

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

See [`azathoth.evaluation`](src/azathoth/evaluation/README.md).

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

See [`azathoth.optimization`](src/azathoth/optimization/README.md).

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

See [`azathoth.runtime`](src/azathoth/runtime/README.md).

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

## Command-Line Application

Installing Azathoth exposes the `azathoth` command.

```bash
azathoth --help
azathoth --version
```

The V1 command hierarchy is:

```text
azathoth
│
├── workflow
│   ├── import
│   ├── list
│   ├── show
│   ├── run
│   ├── optimize
│   ├── promote
│   └── invoke
│
└── model
    ├── list
    ├── show
    ├── authorize
    ├── deauthorize
    └── portfolio
```

The most important distinctions are:

```text
workflow run
    configured workflow execution

workflow invoke
    active production execution


workflow optimize
    empirical search

workflow promote
    explicit production transition


model list
    current provider availability

model portfolio
    organizational authorization
```

See [`azathoth.cli`](src/azathoth/cli/README.md).

## CLI Configuration

The command-line application recognizes:

```text
AZATHOTH_DATABASE
OPENROUTER_API_KEY
```

`AZATHOTH_DATABASE` selects the SQLite application database.

When absent, Azathoth uses:

```text
azathoth.db
```

`OPENROUTER_API_KEY` supplies process-local OpenRouter credentials for provider discovery and executable model composition.

Credentials are not durable workflow configuration.

## First Look

Azathoth includes a canonical prompt-backed workflow:

```text
examples/workflows/simple-prompt.json
```

It is the actual serialized `WorkflowSpecification` representation used by the framework.

Import it:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json
```

List configured workflows:

```bash
azathoth workflow list
```

Inspect the imported workflow:

```bash
azathoth workflow show \
    11111111-1111-1111-1111-111111111111
```

Import, list, and show require no provider credentials.

The repository tests this lifecycle through the installed `azathoth` console script against the same checked-in example.

Provider-dependent execution begins when Azathoth must generate executable prompt-backed candidates.

## Configured Workflow Execution

Execute a configured workflow with:

```bash
azathoth workflow run <WORKFLOW_ID>
```

This executes the configured workflow path:

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

It does not invoke active production state.

## Workflow Optimization

Run empirical workflow optimization with:

```bash
azathoth workflow optimize <WORKFLOW_ID> \
    --expected '<JSON>' \
    --target-latency <SECONDS> \
    --target-cost <USD>
```

Optional:

```bash
--generations <COUNT>
```

The CLI constructs an exact expected outcome from `--expected` and uses the supplied latency and cost targets as workflow scoring inputs.

Optimization does not promote its result.

## Production Promotion

Explicitly promote a configured workflow:

```bash
azathoth workflow promote <WORKFLOW_ID>
```

Promotion persists:

```text
WorkflowProductionState
    current execution authority

WorkflowProductionRevision
    immutable audit history
```

Configured portfolio-based prompt selections are materialized into fixed production model selections.

## Production Invocation

Invoke active production behavior:

```bash
azathoth workflow invoke <WORKFLOW_ID> \
    --input '<JSON>'
```

This command executes `WorkflowProductionState`.

It does not regenerate the configured workflow and does not silently fall back to configured behavior when the workflow has not been deployed.

## Model Operations

Inspect currently available provider models:

```bash
azathoth model list
```

Inspect one model:

```bash
azathoth model show <MODEL_IDENTIFIER>
```

Authorize a currently available model:

```bash
azathoth model authorize <MODEL_IDENTIFIER>
```

Remove organizational authorization:

```bash
azathoth model deauthorize <MODEL_IDENTIFIER>
```

Inspect the authorized portfolio:

```bash
azathoth model portfolio
```

Availability and authorization remain separate concepts.

## Package Guide

The root README describes Azathoth as a complete system.

Detailed architecture lives with each major package.

| Package | Responsibility |
| --- | --- |
| [`azathoth.cli`](src/azathoth/cli/README.md) | Installed operator surface and runtime bootstrap |
| [`azathoth.context`](src/azathoth/context/README.md) | Immutable event-backed working context |
| [`azathoth.goals`](src/azathoth/goals/README.md) | Durable objective intent |
| [`azathoth.strategies`](src/azathoth/strategies/README.md) | Executable strategy contracts and outcomes |
| [`azathoth.execution`](src/azathoth/execution/README.md) | Strategy execution evidence |
| [`azathoth.evaluation`](src/azathoth/evaluation/README.md) | Expected outcomes, evaluators, evidence, and benchmarks |
| [`azathoth.prompting`](src/azathoth/prompting/README.md) | Prompt specifications, bindings, model selection, and executable prompt strategies |
| [`azathoth.providers`](src/azathoth/providers/README.md) | Provider truth, model metadata, authorization, discovery, and executable registries |
| [`azathoth.tools`](src/azathoth/tools/README.md) | Durable tool capabilities, implementations, execution, and verification |
| [`azathoth.workflows`](src/azathoth/workflows/README.md) | Workflow definition, execution, evidence, experiments, and production |
| [`azathoth.optimization`](src/azathoth/optimization/README.md) | Empirical candidate generation and optimization |
| [`azathoth.runtime`](src/azathoth/runtime/README.md) | Process-local executable composition |

Architectural decisions are recorded under [`docs/adrs`](docs/adrs).

## Development

Azathoth uses a strict development toolchain.

Create a virtual environment and install the project with development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the complete quality gate with:

```bash
make check
```

Development emphasizes:

- strict type checking;
- deterministic tests;
- immutable models;
- explicit architectural boundaries;
- test-driven development; and
- ADR-backed design decisions.

Individual checks include:

```bash
ruff format src tests
ruff check src tests
mypy src
pytest
```

## Project Status

Azathoth OSS V1 is in release hardening.

The feature surface is frozen.

The implemented system already spans:

```text
workflow definition
      │
      ▼
runtime candidate generation
      │
      ▼
execution
      │
      ▼
evaluation
      │
      ▼
experimentation
      │
      ▼
optimization
      │
      ▼
explicit promotion
      │
      ▼
production invocation
```

Current release work focuses on:

- public documentation;
- fresh-user onboarding;
- packaging;
- release acceptance testing;
- reproducible examples; and
- operational clarity.

The goal of release hardening is not to expand the architecture.

It is to make the architecture that already exists straightforward to install, understand, verify, and operate.

## Architectural Decisions

Significant architectural decisions are recorded as ADRs under [`docs/adrs`](docs/adrs).

ADRs document public contracts, invariants, and subsystem boundaries.

Package READMEs document the implemented OSS V1 architecture.

## Support the Project

If you find Azathoth useful and would like to support its continued development, you can become a patron here:

**❤️ Patreon:** https://patreon.com/ErisDiscordiaM

Your support helps fund ongoing development, experiments, documentation, testing, and long-term maintenance of the project.

Thank you for helping build better AI systems.

## License

Azathoth is licensed under the terms of the [MIT License](LICENSE).