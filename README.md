# Azathoth

> An optimization engine for AI workflows that learns which strategies work best for different kinds of problems.

## Overview

Azathoth is an experimental platform for optimizing AI systems through empirical evaluation rather than intuition.

Instead of asking:

> "What's the best prompt?"

Azathoth asks:

> "Given this type of context, what combination of prompts, models, tools, retrieval, and workflow consistently produces the best outcome?"

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
Optimization Job
        │
        ▼
Context Analysis
        │
        ▼
Strategy Generation
        │
        ▼
Execution
        │
        ▼
Evaluation
        │
        ▼
Optimization
        │
        ▼
Knowledge Library
```

The output is an optimized strategy rather than a single prompt.

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

result = asyncio.run(
    StrategyExecutor().execute(strategy, context)
)

assert result.output == "I was charged twice."
assert result.initial_context == context
assert result.final_context is not context
```

Run the complete example:

```bash
python examples/execute_strategy.py
```

---

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

---

# Optimization Objectives

Strategies can be optimized against combinations of:

- Quality
- Accuracy
- Cost
- Latency
- Reliability
- Complexity

The optimization objective is configurable depending on the application.

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

Current implementation direction:

- Python
- Pydantic
- FastAPI
- PostgreSQL
- LiteLLM
- pytest

Planned integrations may include:

- Promptfoo
- Braintrust
- LangSmith
- DSPy

The goal is to integrate existing tooling rather than recreate it.

---

# Current Status

Azathoth is in active development.

The current milestone is establishing the core domain model and execution abstractions that will support workflow optimization.

Development is intentionally proceeding in small, testable increments with complete type checking, automated tests, architectural decision records, and continuous integration.

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