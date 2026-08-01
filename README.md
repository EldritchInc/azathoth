# Azathoth

> An optimization engine for AI workflows that learns which strategies work best for different kinds of problems.

## Overview

Azathoth is an experimental platform for optimizing AI systems through empirical evaluation rather than intuition.

Instead of asking:

> "What's the best prompt?"

Azathoth asks:

> "Given this type of context, what combination of strategies, prompts, models, tools, retrieval, and workflow consistently produces the best outcome?"

The goal is to build an optimization engine that can discover, evaluate, and continuously improve AI workflows using real-world examples.

---

# Motivation

Most AI applications contain dozens of hidden decisions:

- Which model should answer?
- Which prompt should be used?
- Should additional information be retrieved?
- Should a tool be called instead?
- Should another question be asked first?
- Is this a single-step or multi-step problem?

These decisions are usually hard-coded by developers.

Azathoth attempts to learn them.

---

# Core Idea

Given:

- a goal
- example contexts
- expected outcomes
- evaluation criteria
- available models and tools

Azathoth searches for the workflow that produces the best results.

That workflow may include:

- prompt selection
- model routing
- retrieval
- tool execution
- clarification questions
- multi-step reasoning

Rather than producing a single "best prompt," Azathoth builds a collection of specialized strategies for different regions of the problem space.

---

# MVP Goals

The initial version focuses on:

- Context-aware routing
- Prompt optimization
- Model arbitrage
- Workflow evaluation
- Strategy selection
- Continuous regression testing

The MVP intentionally does **not** attempt to build autonomous agents or AGI.

---

# High-Level Architecture

```text
Optimization Examples
        │
        ▼
Candidate Strategies
        │
        ▼
Prompt Rendering
        │
        ▼
Language Models
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
        ├── Strategy A × Every Example
        ├── Strategy B × Every Example
        └── Strategy N × Every Example
                    │
                    ▼
            Optimization Runs
                    │
                    ▼
           Strategy Scorecards
                    │
                    ▼
             Strategy Ranker
                    │
                    ▼
            Strategy Ranking
                    │
                    ▼
                 Winner
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

The current implementation can execute candidate strategies across a shared
example set, aggregate their results into evidence-backed scorecards, and rank
the candidates deterministically.

The current implementation includes provider abstractions, executable prompt strategies, context-aware prompt rendering, deterministic experiments, and evidence-backed strategy ranking. Cost-aware model selection and automatic strategy generation remain future milestones.

---

# Core Domain Model

The foundation of Azathoth is a reproducible optimization example.

Every optimization example consists of four core concepts:

- **Goal** — What the system is trying to accomplish.
- **Context** — An immutable, event-backed history describing everything currently known.
- **Expected Outcome** — The result a successful strategy should produce.
- **Comparison Method** — How that outcome should later be evaluated.

This representation allows optimization jobs to be serialized, versioned, replayed, and evaluated consistently across different models and workflows.

```python
from azathoth.context import Context, ContextEvent
from azathoth.evaluation import ExpectedOutcome, OutcomeComparison
from azathoth.goals import Goal
from azathoth.optimization import OptimizationExample

example = OptimizationExample(
    name="Duplicate billing charge",
    goal=Goal(
        name="Classify support requests",
        description="Identify the correct category for each request.",
        success_criteria=("The predicted category matches the expected category.",),
    ),
    context=Context().append(
        ContextEvent(
            event_type="customer.message.received",
            payload={
                "message": "I was charged twice for the same purchase.",
            },
            producer="example",
        )
    ),
    expected_outcome=ExpectedOutcome(
        description="The request is classified as a duplicate charge.",
        value="duplicate_charge",
        comparison=OutcomeComparison.EXACT,
    ),
)
```

Optimization examples can be serialized and restored without losing their structure.

```python
serialized = example.model_dump_json()
restored = OptimizationExample.model_validate_json(serialized)

assert restored == example
```

A runnable version of this example is included in the repository:

```bash
python examples/create_optimization_example.py
```

---

## Current Architecture

The current implementation establishes a complete empirical optimization pipeline.

Today, Azathoth can:

- represent optimization examples as immutable domain models;
- execute deterministic and language-model-backed strategies;
- render prompts from immutable event-backed context;
- evaluate outputs using pluggable evaluators;
- record complete optimization runs;
- aggregate runs into evidence-backed strategy scorecards;
- rank candidate strategies deterministically;
- record provider, model, token usage, latency, and estimated execution cost;
- serialize every stage of the optimization pipeline.

Future work will build on this foundation by generating candidate strategies automatically and optimizing across quality, latency, and cost.

---

# Context as Shared State

Every workflow step can contribute information.

Examples include:

- retrieved documents
- classifications
- tool outputs
- confidence scores
- extracted entities
- user responses
- evaluation results

Rather than mutating shared state, Azathoth records these as immutable context events.

Subsequent workflow steps operate on the accumulated context rather than only the original request.

This provides:

- reproducible executions
- complete execution traces
- provenance tracking
- deterministic replay
- a foundation for continual optimization

---

# Strategy Optimization

Strategies may consist of combinations of:

- Prompt templates
- Language models
- Retrieval steps
- Tool invocations
- Clarification questions
- Multi-step workflows

Each candidate strategy is evaluated against user-defined success criteria.

## Strategy execution

Azathoth strategies operate against immutable, event-backed context.

The execution engine records lifecycle events consistently around every
strategy:

```text
context
   |
   v
strategy.execution.started
   |
   v
strategy output and domain events
   |
   v
strategy.execution.completed
```

A strategy only implements its domain behavior. The executor is responsible for
recording when and how that behavior ran.

```python
import asyncio

from azathoth.context import Context, ContextEvent
from azathoth.execution import StrategyExecutor
from azathoth.strategies import EventFieldStrategy, StrategyMetadata

context = Context().append(
    ContextEvent(
        event_type="customer.message.received",
        payload={"message": "I was charged twice."},
        producer="example",
    )
)

strategy = EventFieldStrategy(
    metadata=StrategyMetadata(
        name="Extract customer message",
        description="Extract the latest customer support message.",
    ),
    event_type="customer.message.received",
    field_name="message",
    output_event_type="customer.message.extracted",
)

result = asyncio.run(StrategyExecutor().execute(strategy, context))

assert result.output == "I was charged twice."
assert result.initial_context == context
assert result.final_context is not context
```

Run the complete example:

```bash
python examples/execute_strategy.py
```

---

## Prompt Strategies

Azathoth treats prompts as executable strategies rather than static strings.

A prompt strategy consists of:

- a prompt template;
- structured bindings into immutable context;
- a language model abstraction.

At execution time the strategy renders a prompt from the current context before executing it through a provider-neutral language model interface.

```text
Context
    │
    ▼
Prompt Template
    │
    ▼
Rendered Prompt
    │
    ▼
Language Model
    │
    ▼
Strategy Output
```

This separation allows prompt rendering, provider selection, evaluation, and optimization to evolve independently.

---

## Language Model Abstractions

Azathoth intentionally separates optimization from model providers.

Every language model implements a common interface regardless of the underlying vendor.

Current execution records include:

- provider;
- model;
- prompt token count;
- completion token count;
- total token count;
- execution latency;
- estimated execution cost.

These measurements become immutable execution evidence that future optimization algorithms can use to balance quality, latency, and cost.

---

## Experiments and strategy ranking

Azathoth can run multiple candidate strategies against the same collection of
optimization examples.

```python
scorecards = await ExperimentRunner().run(
    examples=examples,
    strategies=strategies,
    evaluator=evaluator,
)

ranking = StrategyRanker().rank(scorecards)

winner = ranking.winner
```

For each strategy, the experiment runner produces a `StrategyScorecard`
containing every underlying optimization run.

Scorecards derive their aggregate metrics directly from that evidence:

- run count;
- passed count;
- pass rate;
- mean evaluation score.

The initial ranker uses a deterministic policy that prioritizes pass rate and
mean evaluation score. Experiment execution and ranking are intentionally
separate so future applications can introduce different optimization
objectives without rerunning the experiment.

# Information Acquisition

Sometimes the best next action is not answering the question.

Instead, the system may determine that acquiring one additional piece of information significantly improves expected performance.

Information may come from:

- the user
- retrieval
- external systems
- classifiers
- tools
- previous workflow outputs

Future versions may learn when acquiring information is worth the additional cost.

---

# Evaluation

Evaluation is a first-class component.

Possible evaluators include:

- exact matches
- structured output validation
- classifier scores
- LLM judges
- human review

Multiple evaluators can be combined into a single optimization objective.

Each evaluation produces an immutable `EvaluationResult` containing:

- evaluator identity
- evaluator version
- score
- pass/fail status
- supporting evidence

Evaluation results become part of an `OptimizationRun`, allowing executions to be reproduced, audited, and compared over time.

---

# Optimization Objectives

Strategies can be optimized across one or more objectives including:

- Quality
- Accuracy
- Cost
- Latency
- Reliability
- Complexity
- Token usage
- Provider selection

Different applications may prioritize different tradeoffs.

The optimization objective remains separate from experiment execution, allowing the same evidence to support multiple optimization policies.

---

# Learning

Every workflow execution produces evidence.

Successful strategies become reusable.

Failures become regression tests.

The objective is for the system to improve over time through empirical measurement rather than manual tuning.

---

# Long-Term Direction

The current project focuses on workflow optimization.

Possible future research areas include:

- adaptive context modeling
- automatic workflow discovery
- hierarchical planning
- persistent episodic memory
- continual learning
- autonomous tool creation
- long-running goals

These are intentionally outside the scope of the MVP.

---

# Technology

Current architecture:

- Python
- Pydantic
- AsyncIO
- pytest
- mypy
- Ruff
- GitHub Actions

Planned integrations:

- LiteLLM
- FastAPI
- PostgreSQL
- Promptfoo
- Braintrust
- LangSmith
- DSPy

The goal is to integrate existing tooling rather than recreate it.

---

# Current Status

Azathoth now has a working empirical strategy-comparison pipeline.

Implemented capabilities include:

- immutable goals and optimization examples;
- immutable, event-backed context;
- asynchronous executable strategies;
- traceable strategy execution;
- pluggable evaluators;
- durable optimization runs;
- experiments across multiple strategies and examples;
- evidence-backed strategy scorecards;
- deterministic candidate ranking;
- end-to-end integration coverage;
- strict type checking, automated tests, ADRs, and continuous integration.

The next milestones include:

- provider integrations;
- automatic strategy generation;
- cost-aware model arbitrage;
- optimization across quality, latency, and cost;
- richer evaluation methods;
- workflow optimization across multiple execution steps.

The current architecture intentionally separates execution, evaluation, experimentation, and optimization so these capabilities can be added incrementally.

---

# Guiding Principles

- Optimize with evidence, not intuition.
- Treat prompts as one strategy among many.
- Keep context structured, immutable, and reproducible.
- Separate optimization from execution.
- Make every evaluation reproducible.
- Learn from both success and failure.
- Prefer modular components over framework lock-in.

---

# License

TBD