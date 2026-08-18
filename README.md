# Azathoth

> Empirical optimization for context-aware AI workflows.

Azathoth is an experimental Python framework for building AI systems that improve through measured evidence rather than intuition.

Instead of asking:

> Which prompt or model seems best?

Azathoth asks:

> Given this problem, which combination of workflow, strategy, prompt, model, and execution policy consistently produces the best result?

Azathoth separates specification, execution, evaluation, experimentation, and optimization so each layer can evolve independently while remaining deterministic and testable.

## Why Azathoth?

AI applications routinely make decisions such as:

- which model should handle a request;
- which prompt should be used;
- how context should be constructed;
- whether retrieval or tools are required;
- how a task should be decomposed;
- what should happen when a step fails; and
- which workflow performs best under quality, reliability, latency, and cost constraints.

Those decisions are usually encoded manually.

Azathoth treats them as empirical optimization problems.

The long-term goal is a system capable of generating candidate solutions, executing them against reproducible examples, measuring their behavior, comparing the evidence, and iteratively producing better candidates.

## Who Is This For?

Azathoth is for people building AI systems who want to replace hand-tuned intuition with empirical evidence.

It is particularly relevant for:

- **AI and LLM engineers** comparing prompts, models, providers, and execution strategies;
- **agent and workflow developers** building multi-step systems that need measurable reliability;
- **researchers** experimenting with automated optimization, evaluation, and adaptive AI systems;
- **platform engineers** building provider-independent infrastructure for model selection and execution; and
- **developers exploring self-improving systems** where candidate solutions are generated, tested, measured, and iteratively improved.

Azathoth is not intended to prescribe a single model, provider, prompting technique, or optimization algorithm.

Instead, it provides the infrastructure to ask a more useful question:

> Given the evidence, what actually works best?

## Design Principles

Azathoth is built around a few core principles.

### Evidence over intuition

Optimization decisions should be backed by recorded execution and evaluation evidence.

### Immutable domain models

Important execution and optimization artifacts are immutable so experiments remain reproducible and inspectable.

### Provider independence

Workloads describe requirements rather than hard-coding model providers.

### Explicit boundaries

Execution, evaluation, scoring, ranking, experimentation, and optimization are separate responsibilities.

### Deterministic infrastructure

The optimization substrate should remain deterministic even when the models being evaluated are not.

### Replaceable optimization

Optimization policy remains separate from deterministic execution,
evaluation, scoring, ranking, and experimentation.

Applications may provide their own optimization implementations through
Azathoth's public optimization interfaces.

## Architecture

At the highest level:

```text
Goal
 │
 ▼
Context
 │
 ▼
Strategy
 │
 ▼
Execution
 │
 ▼
Evaluation
 │
 ▼
Optimization
```

Workflows compose strategies into larger executable systems:

```text
WorkflowSpecification
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
        │
        ├───────────────┐
        ▼               ▼
   Statistics      Reliability
        │               │
        └───────┬───────┘
                ▼
        EvaluationResult
                │
                ▼
        WorkflowScorer
                │
                ▼
       WorkflowScorecard
                │
                ▼
        WorkflowRanker
                │
                ▼
     WorkflowExperiment
                │
                ▼
       WorkflowOptimizer
                │
                ▼
  Optimization Generation
                │
                ▼
  Optimization Session
```

This separation allows execution mechanics, scoring policy, ranking behavior, and optimization algorithms to change independently.

## Current Capabilities

Azathoth currently provides:

- immutable event-backed context;
- durable goals and expected outcomes;
- executable strategy protocols;
- deterministic strategy execution;
- provider-neutral model requirements;
- model catalogs and executable model registries;
- prompt-backed strategies;
- deterministic prompt candidate generation;
- model binding validation;
- workflow specifications;
- dependency-graph validation;
- dependency-layer execution;
- workflow value export and downstream binding;
- conditional workflow execution;
- retry policies;
- workflow failure policies;
- durable step-attempt history;
- execution statistics;
- normalized reliability metrics;
- deterministic workflow scoring;
- workflow scorecards;
- deterministic workflow ranking;
- workflow experiments;
- workflow optimization protocols;
- replay optimization; and
- multi-generation optimization sessions.

The current optimization substrate is intentionally conservative.

`ReplayWorkflowOptimizer` does not improve candidates. It exists as a deterministic reference implementation that proves the optimization boundary and iterative session orchestration before adaptive optimization strategies are introduced.

## Package Guide

The root README describes the system as a whole.

Detailed documentation lives with each major package.

| Package | Responsibility |
| --- | --- |
| [`azathoth.context`](src/azathoth/context/README.md) | Immutable event-backed working context |
| [`azathoth.goals`](src/azathoth/goals/README.md) | Desired outcomes and success criteria |
| [`azathoth.strategies`](src/azathoth/strategies/README.md) | Executable strategy contracts and outcomes |
| [`azathoth.execution`](src/azathoth/execution/README.md) | Strategy execution and durable execution results |
| [`azathoth.evaluation`](src/azathoth/evaluation/README.md) | Expected outcomes, evaluators, and evaluation evidence |
| [`azathoth.prompting`](src/azathoth/prompting/README.md) | Prompt strategies, templates, bindings, and candidate generation |
| [`azathoth.providers`](src/azathoth/providers/README.md) | Provider-neutral model metadata, requirements, discovery, and registries |
| [`azathoth.tools`](src/azathoth/tools/README.md) | executable tools callable from workflow steps. |
| [`azathoth.workflows`](src/azathoth/workflows/README.md) | Multi-step workflow specification, execution, scoring, ranking, and experiments |
| [`azathoth.optimization`](src/azathoth/optimization/README.md) | Empirical experiments, workflow optimization, and optimization sessions |

Architectural decisions are recorded separately in [`docs/adr`](docs/adr).

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

Strategies receive context without mutating shared state.

See [`azathoth.context`](src/azathoth/context/README.md).

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

Strategies may be deterministic operations, prompt-backed model calls, or future retrieval and tool strategies.

See [`azathoth.strategies`](src/azathoth/strategies/README.md).

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

Evaluation answers whether an output satisfied an expectation.

It is separate from workflow scoring, which interprets broader execution evidence such as reliability, latency, and cost.

See [`azathoth.evaluation`](src/azathoth/evaluation/README.md).

## Workflow Benchmarks

Azathoth can execute reusable benchmark datasets against multiple workflow
candidates.

```text
Benchmark Dataset
        │
        ▼
Workflow Candidates
        │
        ▼
Workflow Execution
        │
        ▼
Workflow Evaluation
        │
        ▼
Workflow Scorecards
        │
        ▼
Workflow Ranking
```

Benchmark execution reuses the same deterministic workflow execution,
evaluation, and ranking infrastructure already used elsewhere throughout the
system.

This provides the objective evidence required for provider comparison, routing,
and future optimization.

# Providers

The providers package separates durable execution requests from provider
implementations.

```text
Prompt
   │
   ▼
ModelRequest
   │
   ▼
ModelExecutor
   │
   ▼
LanguageModel
   ├──────────────┐
   ▼              ▼
Deterministic  Future OpenRouter
   │
   ▼
ModelResponse
```

Model requests establish a stable execution boundary for future provider
integrations.

Execution remains deterministic while allowing future providers to introduce
additional execution capabilities without changing higher-level workflow
execution.

## OpenRouter

Azathoth's first production language model provider is OpenRouter.

```text
Prompt
   │
   ▼
ModelRequest
   │
   ▼
ModelExecutor
   │
   ▼
OpenRouterLanguageModel
   │
   ▼
OpenRouter
   │
   ▼
ModelResponse
```

Normal automated tests remain deterministic through mocked HTTP transports.

Live OpenRouter verification is available through an explicit opt-in smoke test,
allowing development and continuous integration to execute without consuming API
credits.

See [`azathoth.providers`](src/azathoth/providers/README.md).

## Workflow Execution

Azathoth workflows now execute against production language models through the
provider abstraction.

```text
Workflow Specification
          │
          ▼
Workflow Candidate
          │
          ▼
Workflow Runner
          │
          ▼
Prompt Strategy
          │
          ▼
Language Model
          │
          ▼
OpenRouter
          │
          ▼
Workflow Run
```

Provider-backed workflow execution preserves the same deterministic execution,
evaluation, and scorecard infrastructure already used by deterministic language
models.

Normal automated tests remain fully deterministic.

Production execution is verified through explicit opt-in smoke tests.

### Tool-Backed Workflows

Durable tools can execute as normal workflow steps.

```text
ToolRequirement
      │
      ▼
Persisted Tool Definition
      │
      ▼
Resolved Implementation
      │
      ▼
ToolStrategy
      │
      ▼
WorkflowValue
      │
      ▼
WorkflowCondition
```

Workflow specifications reference tool capabilities rather than concrete
implementations.

Candidate generation resolves executable implementations before runtime.

Tool-backed steps then participate in the same dependency, input-binding,
output-binding, retry, failure, and conditional-execution infrastructure as
other workflow strategies.

This allows deterministic persisted capabilities to participate in workflows
without baking their implementation source into Azathoth.

# Tools

The tools package separates capability contracts from executable
implementations.

```text
ToolRequirement
       │
       ▼
 ToolResolver
       │
       ▼
ToolDefinition
       │
       ▼
ToolImplementationResolver
       │
       ▼
ToolImplementation
       │
       ▼
PythonToolExecutor
       │
       ▼
 ToolVerifier
       │
       ▼
ToolVerification
```

Capability resolution identifies *what* satisfies a required capability.

Implementation resolution identifies *how* that capability can be executed.

Execution and verification remain deterministic and independent of
optimization.

This architecture keeps capability identity, implementation resolution,
execution, and verification independent so applications can extend tool
behavior without coupling it to workflow execution.

See [`azathoth.tools`](src/azathoth/tools/README.md).

## Persistent Tools

Azathoth tools can exist as durable data rather than application-specific source
files.

```text
Tool Definition
      +
Implementation Source
      +
Test Cases
      │
      ▼
Persistent Repository
      │
      ▼
Immutable Tool Catalogs
      │
      ▼
Resolution
      │
      ▼
Execution and Verification
```

The current repository implementations include in-memory storage and SQLite.

Persisted tools retain:

- capability identity and schemas;
- executable runtime and source;
- implementation version;
- deterministic verification cases.

Tool catalogs and resolvers remain storage independent.

This establishes the foundation for dynamically registered, synthesized, and
eventually optimizer-generated tools without requiring those tools to be baked
into the Azathoth codebase.

### Workflows

A workflow specification describes a dependency graph without embedding executable model instances.

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

Execution proceeds in dependency-safe layers while preserving deterministic commit order.

See [`azathoth.workflows`](src/azathoth/workflows/README.md).

### Durable Workflows

Workflow specifications can be persisted independently from executable runtime
objects.

```text
SQLite
  │
  ▼
WorkflowSpecification
  │
  ▼
WorkflowCatalog
  │
  ▼
Candidate Generation
  │
  ▼
WorkflowRunner
```

Persisted workflows retain their dependency graph, bindings, conditions,
retries, failure policies, prompt requirements, and tool requirements.

Executable model and tool implementations are resolved only when a persisted
specification becomes a workflow candidate.

This keeps durable workflow configuration independent from runtime provider and
tool objects.

### Durable Execution Evidence

Completed workflow executions can be persisted independently from workflow
definitions.

```text
WorkflowSpecification
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
        │
        ▼
WorkflowRunRepository
        │
        ▼
Persistent Evidence
```

Each `WorkflowRun` has a stable identifier and retains step execution results,
attempts, values, contexts, and timing.

Later human or application feedback is stored separately.

```text
WorkflowRun
    │
    │ run_id
    ▼
WorkflowRunFeedback
├── good / bad
├── reason
└── corrected output
```

Feedback does not modify the original execution record.

This keeps observed runtime behavior separate from later judgments about that
behavior.

### Workflow Experiments

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
        │
        ▼
      winner
```

Experiments contain no candidate-generation or mutation logic.

Their job is to produce empirical evidence about a candidate population.

### Optimization

Optimization consumes experiment evidence and proposes the next population.

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
          │
          ▼
 Next Generation
```

Optimization sessions repeat this process across generations:

```text
Initial Population
        │
        ▼
Experiment
        │
        ▼
Optimizer
        │
        ▼
Generation 1
        │
        ▼
Experiment
        │
        ▼
Optimizer
        │
        ▼
Generation 2
        │
        ▼
       ...
```

See [`azathoth.optimization`](src/azathoth/optimization/README.md).

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

## Project Status

Azathoth is under active development.

The deterministic execution, evaluation, benchmarking, and optimization
substrate is established.

Current public development focuses on completing the reusable runtime and its
extension boundaries, including:

- durable specifications and empirical evidence;
- tool-backed workflow execution;
- production-oriented persistence;
- provider and evaluator integrations;
- command-line interfaces; and
- reproducible end-to-end examples.

Optimization algorithms remain replaceable application-level components.

## Architectural Decisions

Significant architectural decisions are recorded as ADRs under
[`docs/adrs`](docs/adrs).

ADRs document public contracts, invariants, and subsystem boundaries.

Package READMEs document the behavior of the open-source runtime.

## Support the Project

If you find Azathoth useful and would like to support its continued development, you can become a patron here:

**❤️ Patreon:** https://patreon.com/ErisDiscordiaM

Your support helps fund ongoing development, experiments, documentation, testing, and long-term maintenance of the project.

Thank you for helping build better AI systems.

## License

Azathoth is licensed under the terms of the [MIT License](LICENSE).