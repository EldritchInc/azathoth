# Azathoth

> An optimization engine for AI workflows that learns which strategies
> work best through empirical evaluation rather than intuition.

## Overview

Azathoth is an experimental platform for optimizing AI systems by
separating **specification**, **execution**, **evaluation**, and
**optimization**.

Instead of asking:

> "What's the best prompt?"

Azathoth asks:

> "Given this kind of problem, which combination of workflows,
> strategies, prompts, models, tools, retrieval, and evaluation
> consistently produces the best outcome?"

The project is intentionally built from durable domain models upward so
every optimization experiment is reproducible, versionable, and
evidence-backed.

------------------------------------------------------------------------

## Support the Project

Azathoth is developed in public as an open-source project.

Support ongoing development:

**https://patreon.com/ErisDiscordiaM**

------------------------------------------------------------------------

# Motivation

Most AI systems embed important decisions directly into application
code:

-   Which model should answer?
-   Which prompt should be used?
-   Should retrieval be performed?
-   Should a tool be called?
-   Should another question be asked first?
-   Should this become a multi-step workflow?

These choices are usually based on intuition.

Azathoth treats them as optimization problems.

------------------------------------------------------------------------

# High-Level Architecture

``` text
Optimization Examples
        │
        ▼
Workflow Specifications
        │
        ▼
Workflow Step Specifications
        │
        ▼
Prompt Strategy Specifications
        │
        ▼
Model Requirements
        │
        ▼
Model Discovery
        │
        ▼
Candidate Generation
        │
        ▼
Executable Strategies
        │
        ▼
Strategy Execution
        │
        ▼
Evaluation
        │
        ▼
Optimization Runs
        │
        ▼
Experiment Runner
        │
        ▼
Strategy Scorecards
        │
        ▼
Strategy Ranking
        │
        ▼
Best Candidate
```

The architecture intentionally separates:

-   durable specifications
-   runtime execution
-   evaluation
-   optimization

so each layer can evolve independently.

------------------------------------------------------------------------

# Core Domain Model

Every optimization example combines:

-   Goal
-   Immutable Context
-   Expected Outcome
-   Comparison Method

These examples are durable, serializable, and replayable.

------------------------------------------------------------------------

# Context as Shared State

Context is immutable and event-backed.

Workflow steps append new events rather than mutating shared state.

This provides:

-   deterministic replay
-   execution provenance
-   complete traces
-   reproducible optimization

------------------------------------------------------------------------

# Workflow Specifications

Azathoth represents workflows as durable dependency graphs.

A workflow describes *what* work should be performed without embedding runtime execution concerns.

Each workflow consists of:

- workflow metadata;
- workflow step specifications; and
- explicit dependency relationships between workflow steps.

```text
Workflow
      │
      ▼
 Step A
  │   │
  ▼   ▼
Step B Step C
   \   /
    ▼ ▼
   Step D
```

Each workflow step owns its own executable specification.

Today that specification is a prompt strategy specification.

Future workflow step types may include:

- prompt strategies;
- retrieval;
- tool invocation;
- deterministic computation;
- conditional routing; and
- human review.

Importantly, execution requirements remain **step-scoped**.

Different workflow steps may require different:

- language models;
- context windows;
- model capabilities;
- execution policies; and
- tools.

Workflow specifications intentionally contain no executable language models, runtime schedulers, or execution state.

## Workflow Candidates

Workflow specifications describe *what* work should be performed.

Before execution, Azathoth transforms a workflow specification into an executable workflow candidate.

```text
WorkflowSpecification
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner (future)
```

Workflow candidate generation binds each workflow step independently.

```text
Workflow Specification

Step A
  Structured Output

Step B
  Tool Use

        │
        ▼

Workflow Candidate

Step A
  provider-a/classifier

Step B
  provider-b/reasoner
```

Importantly, workflow candidate generation preserves:

- workflow metadata;
- dependency topology;
- execution ordering;
- step-scoped model requirements; and
- deterministic workflow structure.

Workflow candidates intentionally remain runtime objects.

They contain executable strategies while preserving the dependency graph defined by the workflow specification.

This separation allows durable workflow definitions to remain provider-neutral while enabling execution against concrete language model implementations.

## Dependency Planning

Workflow specifications expose deterministic execution layers.

Each layer contains workflow steps whose dependencies have already been satisfied.

```text
Layer 1
──────────────
Classify Request
Detect Question

Layer 2
──────────────
Retrieve Documents

Layer 3
──────────────
Reason About Answer
```

Execution layers preserve declared workflow order while exposing opportunities for future parallel execution.

This separation allows workflow definitions to remain durable, serializable, and provider-neutral while providing a stable foundation for future workflow execution and optimization.

------------------------------------------------------------------------

# Prompt Strategy Specifications

Prompt strategy specifications describe workloads independently of any
concrete language model.

They define:

-   prompt
-   metadata
-   model requirements

They do not select providers or implementations.

------------------------------------------------------------------------

# Model Requirements

Model requirements describe the workload, not the provider.

Examples include:

-   required capabilities
-   supported modalities
-   minimum context window
-   minimum output size
-   optional pricing constraints

Requirements remain provider-neutral.

------------------------------------------------------------------------

# Model Discovery

Model requirements are converted into queries against a model catalog.

The catalog answers:

> Which models are capable of executing this workload?

Selection happens later through empirical optimization.

------------------------------------------------------------------------

# Candidate Generation

Candidate generation combines:

-   prompt strategy specifications
-   model requirements
-   model catalog
-   executable model registry

to produce executable prompt strategies.

Each generated candidate has:

-   deterministic identity
-   explicit model binding
-   independent execution evidence

------------------------------------------------------------------------

# Model Binding

Generated candidates are permanently bound to a single executable model.

During execution Azathoth validates that the responding model matches
the configured binding before accepting execution evidence.

This guarantees that scorecards and optimization results are always
attributed to the correct executable strategy.

------------------------------------------------------------------------

# Strategy Execution

Prompt-backed strategies share a common execution pipeline:

1.  invoke language model
2.  validate model binding
3.  collect execution metrics
4.  construct strategy outcome

Execution remains provider-neutral.

------------------------------------------------------------------------

# Execution Metrics

Every execution records immutable operational evidence including:

-   provider
-   model
-   token usage
-   latency
-   estimated cost

These metrics become optimization evidence.

------------------------------------------------------------------------

# Experiments

Experiments execute many candidate strategies across the same
optimization examples.

Each execution produces an OptimizationRun.

Runs aggregate into StrategyScorecards.

Scorecards are ranked deterministically.

Execution, evaluation, and ranking remain separate architectural
concerns.

------------------------------------------------------------------------

# Evaluation

Evaluators are pluggable.

Potential evaluators include:

-   exact match
-   structured validation
-   classifier scoring
-   LLM judges
-   human review

Each evaluation produces immutable evidence.

------------------------------------------------------------------------

# Current Implementation

Current capabilities include:

-   immutable optimization examples
-   immutable event-backed context
-   workflow specifications
-   workflow step specifications
-   prompt strategy specifications
-   provider-neutral model requirements
-   capability-based model discovery
-   deterministic candidate generation
-   validated model binding
-   shared prompt execution
-   asynchronous strategy execution
-   pluggable evaluators
-   optimization runs
-   experiment execution
-   strategy scorecards
-   deterministic ranking
-   comprehensive tests
-   strict typing
-   continuous integration

------------------------------------------------------------------------

# Long-Term Direction

Planned work includes:

-   provider integrations
-   workflow candidate generation
-   workflow orchestration
-   adaptive model selection
-   cost-aware optimization
-   richer evaluation
-   automatic strategy generation
-   continual learning

------------------------------------------------------------------------

# Guiding Principles

-   Optimize with evidence, not intuition.
-   Separate specification from execution.
-   Keep context immutable and reproducible.
-   Keep providers behind abstractions.
-   Treat prompts as one strategy among many.
-   Allow different workflow steps to use different models and tools.
-   Make optimization reproducible.

------------------------------------------------------------------------

# Technology

Current:

-   Python
-   Pydantic
-   AsyncIO
-   pytest
-   mypy
-   Ruff
-   GitHub Actions

Planned:

-   LiteLLM
-   FastAPI
-   PostgreSQL
-   Promptfoo
-   Braintrust
-   LangSmith
-   DSPy

------------------------------------------------------------------------

# License

TBD
