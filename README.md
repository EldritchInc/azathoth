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

### Intelligence above the substrate

LLM-driven mutation, planning, and synthesis belong on top of a testable execution and optimization foundation rather than inside it.

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

### Providers

Model-backed workloads declare `ModelRequirements`.

Configured models are described by `ModelMetadata` and discovered through `ModelCatalog`.

Executable implementations are resolved separately through `LanguageModelRegistry`.

```text
ModelRequirements
        │
        ▼
    ModelQuery
        │
        ▼
   ModelCatalog
        │
        ▼
eligible models
        │
        ▼
LanguageModelRegistry
        │
        ▼
executable model
```

This keeps workload requirements independent from provider implementations.

See [`azathoth.providers`](src/azathoth/providers/README.md).

# Tools

The tools package models durable capabilities independently of execution,
verification, and optimization.

```text
                 ToolRequirements
                        │
                        ▼
                 ToolRequirement
                        │
                        ▼
                   ToolResolver
                  /            \
                 ▼              ▼
          ToolCatalog      ToolMatcher
                 \              /
                  ▼            ▼
                 ToolDefinition
                  /           \
                 ▼             ▼
      ToolImplementation   ToolTestCase
                 │             │
                 ▼             │
          ToolExecutor         │
                 │             │
                 └──────┬──────┘
                        ▼
                  ToolVerifier
                        │
                        ▼
                ToolVerification
```

Workflows describe required capabilities rather than executable implementations.

Deterministic requirement resolution produces candidate capability definitions.

Execution and verification remain independent of capability discovery.

This architecture establishes the foundation for future runtime selection,
persistent registries, adaptive capability routing, synthesized tools, and
optimization.

See [`azathoth.tools`](src/azathoth/tools/README.md).

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

The deterministic execution and optimization substrate is established.

Current development is moving toward optimizers that can produce genuinely different candidate populations while preserving the same experiment and session infrastructure.

Near-term areas include:

- candidate mutation;
- candidate lineage and provenance;
- prompt evolution;
- model exploration and arbitrage;
- multi-objective optimization;
- structural workflow mutation; and
- LLM-guided candidate generation.

Longer-term areas include:

- retrieval strategies;
- tool strategies;
- planner and verifier strategies;
- episodic memory;
- automatic benchmark generation;
- adaptive routing;
- workflow synthesis; and
- empirical self-improvement.

## Architectural Decisions

Significant architectural decisions are recorded as ADRs under [`docs/adr`](docs/adr).

ADRs explain why important boundaries and behaviors exist.

Package READMEs document how each subsystem works.

The root README provides the system-level map.

## Support the Project

If you find Azathoth useful and would like to support its continued development, you can become a patron here:

**❤️ Patreon:** https://patreon.com/ErisDiscordiaM

Your support helps fund ongoing development, experiments, documentation, testing, and long-term maintenance of the project.

Thank you for helping build better AI systems.

## License

Azathoth is licensed under the terms of the [MIT License](LICENSE).