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

# Workflow Execution

Executable workflows are represented by `WorkflowCandidate`.

A workflow candidate contains executable workflow steps while preserving the dependency graph defined by its originating workflow specification.

Workflow execution is performed by `WorkflowRunner`.

Workflow execution proceeds one dependency layer at a time.

```text
Layer 0
──────────────
Classifier

        │

Layer 1
──────────────
Question Detector
Retrieve Context

        │

Layer 2
──────────────
Reason About Answer
```

## Dependency Layer Semantics

Every workflow step within a dependency layer receives the same immutable starting context.

```text
Layer Context
     │
     ├── Step A
     └── Step B
```

Workflow step outputs are merged only after every workflow step in the dependency layer completes successfully.

Outputs are merged in declared workflow order to guarantee deterministic behavior.

This allows future implementations to execute independent workflow steps concurrently without changing observable workflow behavior.

## Failure Semantics

Dependency layers form atomic execution boundaries.

If any workflow step within a dependency layer fails:

- workflow execution terminates immediately;
- no outputs produced by that dependency layer are merged into workflow context;
- previously completed dependency layers remain committed; and
- the original workflow step exception propagates to the caller.

These semantics provide deterministic behavior while avoiding rollback of previously completed workflow layers.

## Separation of Responsibilities

Workflow execution is intentionally decomposed into independent responsibilities.

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
StrategyExecutor
        │
        ▼
Strategy
```

This separation allows workflow orchestration to remain independent of individual execution mechanisms.

Individual workflow steps remain free to use different:

- language models;
- model capabilities;
- context windows;
- execution policies; and
- tools.

Future workflow step types may therefore execute prompt strategies, retrieval strategies, tool invocations, deterministic computation, or human review without changing workflow orchestration.

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

# Workflow Values

Workflow steps may export structured values for later workflow processing.

Workflow values are declared explicitly using `WorkflowValueBinding`.

```text
Execution Output
──────────────────────────────────────

{
    "classification": "math",
    "confidence": 0.98
}

↓

WorkflowValueBinding

classification → ("classification")
confidence     → ("confidence")

↓

WorkflowValue
```

Workflow value bindings are preserved from workflow specification through executable workflow candidates.

During execution each binding resolves against the workflow step output.

The resolved values are recorded as immutable `WorkflowValue` instances.

## Querying Workflow Values

Workflow runs expose deterministic query operations.

```python
run.values

run.values_named("classification")

run.values_from(step_id)
```

Workflow values preserve execution order.

Multiple workflow steps may export workflow values with the same name.

Workflow value names are therefore not globally unique.

Queries return every matching value in deterministic workflow execution order.

## Workflow Values vs Context

Workflow values intentionally differ from workflow context.

Workflow context records execution history and evidence.

Workflow values record structured conclusions intentionally exported by workflow steps.

```text
Context
──────────────
Evidence
History
Observations

Workflow Values
──────────────
Classification
Confidence
Retrieved Documents
Tool Results
Intermediate Reasoning
```

Keeping these concepts separate allows workflow orchestration, routing, and optimization to evolve independently from long-lived contextual reasoning.

------------------------------------------------------------------------

# Workflow Value Dataflow

Workflow values are explicitly connected between workflow steps.

Each producing workflow step declares exported values.

Each consuming workflow step declares the workflow values it requires.

```text
Classifier
──────────────

exports

classification

        │
        ▼

Workflow Value

        │
        ▼

Workflow Value Reference

        │
        ▼

Reasoner

input:
route
```

Workflow value identity consists of:

- producer workflow step; and
- workflow value name.

This allows multiple workflow steps to export values with identical names while remaining unambiguous.

## Validation

Workflow specifications validate workflow dataflow before execution.

Validation ensures that:

- producer workflow steps exist;
- referenced workflow values exist;
- producer workflow steps are upstream dependencies;
- exported workflow value names are unique per workflow step; and
- input names are unique per consuming workflow step.

Invalid workflow graphs fail during specification validation rather than runtime execution.

## Runtime Resolution

Workflow input bindings resolve immediately before strategy execution.

Resolved workflow inputs are added to the consuming workflow step's execution context.

These temporary input bindings are intentionally excluded from the shared workflow context after execution.

This separation preserves the distinction between:

- workflow execution history; and
- workflow dataflow.

------------------------------------------------------------------------

```markdown

# Conditional Workflow Execution

Workflow steps may conditionally execute based on values produced by upstream workflow steps.

Conditions use the same producer-qualified workflow value references used by workflow input bindings.

```text

Classifier

──────────────

exports:

classification = "math"

        │

        ▼

WorkflowCondition

classification == "math"

        │

        ▼

Math Reasoner
```

A workflow condition identifies:

* the workflow step that produced the value;
* the exported workflow value name; and
* the value required for the condition to match.

For example:

```text
WorkflowCondition(
    source=WorkflowValueReference(
        producer_step_id=classifier_step_id,
        name="classification",
    ),
    expected="math",
)
```

Validation

Conditional dataflow is validated as part of the workflow specification.

Azathoth verifies that:

* the referenced producer exists;
* the producer exports the referenced workflow value; and
* the producer executes upstream of the conditional step.

Invalid conditional workflows therefore fail before candidate generation or execution.

Execution Semantics

A workflow step with no conditions executes normally.

When conditions are present, every condition must be satisfied before the workflow step becomes eligible.

```text
No conditions
        │
        ▼
     Execute


Condition A ── true ──┐
                      ├── Execute
Condition B ── true ──┘


Condition A ── true
Condition B ── false
        │
        ▼
       Skip
```

Conditions currently use equality comparison.

Multiple conditions use logical AND semantics.

A referenced workflow value that is unavailable is treated as an unsatisfied condition.

This allows conditional branches to propagate naturally when an upstream branch was skipped.

Executed and Skipped Steps

Workflow runs explicitly distinguish between executed and skipped workflow steps.

```text
WorkflowStepStatus.EXECUTED

WorkflowStepStatus.SKIPPED
```

Executed steps retain their complete execution evidence and exported workflow values.

Skipped steps:

* contain no execution result;
* produce no workflow values; and
* remain present in the workflow run.

This preserves the complete workflow topology in execution traces without fabricating evidence for work that never occurred.

Adaptive Workflows

Conditional execution allows workflow topology, structured dataflow, and step-specific execution configuration to compose naturally.

```text
                    Classifier
                        │
                 classification
                   /         \
                  /           \
             "math"         "general"
                │               │
                ▼               ▼
         Math Reasoner    General Reasoner
          Model A             Model B
          Tool X              Tool Y
```

Each workflow step remains independently configured.

A conditional workflow therefore does not require a workflow-wide language model, tool, or execution policy.

This provides the foundation for adaptive routing while preserving Azathoth’s step-scoped execution architecture.

------------------------------------------------------------------------

# Workflow Condition Operators

Workflow conditions compare workflow values using explicit comparison operators.

```text
Workflow Value
        │
        ▼
WorkflowCondition
        │
        ▼
comparison
        │
        ▼
execute or skip
```

Supported operators include:

| Operator | Meaning |
|----------|---------|
| `==` | Equal |
| `!=` | Not Equal |
| `>` | Greater Than |
| `>=` | Greater Than or Equal |
| `<` | Less Than |
| `<=` | Less Than or Equal |

For example:

```python
WorkflowCondition(
    source=WorkflowValueReference(
        producer_step_id=classifier_step_id,
        name="confidence",
    ),
    operator=WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
    expected=0.90,
)
```

Equality operators support any JSON value.

Ordering operators require numeric operands.

This allows workflows to naturally express routing decisions such as:

- confidence thresholds;
- document counts;
- evaluation scores;
- latency limits; and
- optimization metrics.

Workflow comparison semantics are implemented by `WorkflowCondition`.

Workflow execution remains responsible only for resolving workflow values and evaluating workflow eligibility.

------------------------------------------------------------------------

# Workflow Retry Policies

Workflow steps may define retry behavior independently.

```text
Workflow Step
      │
      ▼
Retry Policy
      │
      ▼
Workflow Runner
      │
      ▼
attempt
      │
success? ─────► complete
      │
      ▼
retry
```

Retry policies are configured per workflow step.

```python
WorkflowRetryPolicy(
    max_attempts=3,
    initial_delay_seconds=0.5,
    backoff_multiplier=2.0,
    maximum_delay_seconds=5.0,
)
```

A retry policy specifies:

- maximum execution attempts;
- initial retry delay;
- exponential backoff multiplier; and
- optional maximum retry delay.

`max_attempts` includes the initial execution.

For example:

```text
max_attempts = 3

Attempt 1
↓

Attempt 2
↓

Attempt 3
```

Retry behavior is implemented by `WorkflowRunner`.

Strategies remain unaware of retries and simply succeed or fail.

This separation keeps workflow orchestration responsible for execution policy while allowing individual workflow steps to configure retry behavior independently.

Retry policies compose naturally with:

- workflow dependency layers;
- workflow values;
- conditional execution; and
- step-specific model and tool configuration.

The current implementation computes retry delays but intentionally performs retries immediately.

This preserves deterministic execution while establishing the durable retry architecture.

------------------------------------------------------------------------

# Workflow Step Attempt History

Every workflow execution attempt is recorded.

```text
Workflow Step
      │
      ▼
Attempt 1
      │
failure
      ▼
Attempt 2
      │
failure
      ▼
Attempt 3
      │
success
      ▼
Workflow Step Run
```

Each attempt records:

- attempt number;
- start time;
- completion time;
- either:
  - a successful execution result; or
  - a recorded failure.

Successful executions continue to be exposed directly through the workflow step.

Attempt history provides the complete execution history that produced the final result.

This enables durable execution auditing while preserving a simple interface for successful workflow execution.

Execution history forms the foundation for future capabilities such as:

- reliability metrics;
- provider comparisons;
- optimization feedback;
- execution analytics; and
- adaptive workflow selection.

------------------------------------------------------------------------

# Workflow Failure Policies

Workflow steps independently define how permanent execution failures are handled.

```text
Workflow Step
      │
      ▼
Retry Policy
      │
      ▼
Retries Exhausted
      │
      ▼
Failure Policy
```

Failure policies are configured per workflow step.

```python
WorkflowFailurePolicy.FAIL_WORKFLOW

WorkflowFailurePolicy.CONTINUE

WorkflowFailurePolicy.SKIP_DEPENDENTS
```

## FAIL_WORKFLOW

Abort workflow execution immediately.

The original exception is propagated after retry exhaustion.

```text
failure
   │
   ▼
workflow aborts
```

## CONTINUE

Record the failed workflow step while allowing remaining workflow execution to continue.

Failed workflow steps do not produce workflow values.

Independent workflow branches continue normally.

```text
failure
   │
   ▼
FAILED
   │
   ├── remaining workflow continues
   └── missing workflow values remain unavailable
```

## SKIP_DEPENDENTS

Record the failed workflow step.

Every transitive dependent workflow step is skipped.

Independent workflow branches continue.

```text
failed
   │
   ├── dependent
   │      │
   │      ▼
   │   skipped
   │
   └── independent
          │
          ▼
      executed
```

Failure policies compose naturally with:

- workflow dependency layers;
- workflow values;
- conditional execution;
- retry policies; and
- execution attempt history.

Together these provide deterministic, fault-tolerant workflow orchestration while preserving immutable workflow execution records.

------------------------------------------------------------------------

# Workflow Execution Statistics

Every recorded workflow execution exposes deterministic execution statistics.

Statistics are computed directly from durable workflow execution records.

```text
WorkflowRun
      │
      ▼
WorkflowRunStatistics
```

The statistics summarize:

- workflow step counts;
- execution attempt counts;
- retry count; and
- total execution duration.

```python
statistics = run.statistics

statistics.total_steps
statistics.executed_steps
statistics.failed_steps
statistics.skipped_steps

statistics.total_attempts
statistics.successful_attempts
statistics.failed_attempts

statistics.retry_count

statistics.duration_seconds
```

`WorkflowRun` also exposes convenience properties for common queries.

```python
run.succeeded
run.failed

run.retry_count

run.duration_seconds

run.executed_step_count
run.failed_step_count
run.skipped_step_count

run.total_attempt_count
```

Execution statistics are derived rather than persisted.

This guarantees that execution summaries always remain consistent with the recorded workflow history while avoiding duplicated state.

These statistics provide the foundation for future capabilities including:

- execution dashboards;
- provider comparisons;
- workflow benchmarking;
- optimization feedback; and
- adaptive workflow planning.

------------------------------------------------------------------------

# Workflow Reliability Metrics

Workflow runs expose normalized reliability metrics derived from recorded execution history.

```text
WorkflowRun
      │
      ▼
WorkflowRunStatistics
      │
      ▼
WorkflowReliabilityMetrics
```

Reliability metrics summarize execution quality independently of workflow size.

```python
metrics = run.reliability

metrics.completion_rate

metrics.first_attempt_success_rate

metrics.retry_rate

metrics.failure_rate
```

## Completion Rate

Fraction of workflow steps that completed successfully.

```text
executed workflow steps
────────────────────────
total workflow steps
```

## First-Attempt Success Rate

Fraction of attempted workflow steps that succeeded on their first execution attempt.

```text
first-attempt successes
───────────────────────
attempted workflow steps
```

## Retry Rate

Fraction of attempted workflow steps requiring one or more retries.

```text
retried workflow steps
──────────────────────
attempted workflow steps
```

## Failure Rate

Fraction of attempted workflow steps that permanently failed.

```text
failed workflow steps
─────────────────────
attempted workflow steps
```

Skipped workflow steps are excluded from attempt-based reliability metrics because they were never executed.

Reliability metrics are computed rather than persisted, ensuring they always remain consistent with recorded workflow execution history.

These metrics establish the foundation for future workflow evaluation, provider benchmarking, execution analytics, and automatic optimization.

------------------------------------------------------------------------

# Workflow Evaluation

Workflow runs expose immutable evaluation objects.

Evaluations provide a stable interface between workflow execution and higher-level analysis.

```text
WorkflowRun
      │
      ▼
WorkflowEvaluation
      ├── WorkflowRunStatistics
      └── WorkflowReliabilityMetrics
```

```python
evaluation = run.evaluation

evaluation.workflow_id

evaluation.statistics

evaluation.reliability

evaluation.evaluated_at
```

Workflow evaluations intentionally contain objective execution observations.

They do not include optimization scores or ranking heuristics.

This separation allows optimization systems to evolve independently while preserving deterministic workflow execution.

Workflow evaluations establish the foundation for future capabilities including:

- workflow benchmarking;
- provider comparison;
- execution dashboards;
- optimization pipelines;
- candidate ranking; and
- adaptive workflow selection.

------------------------------------------------------------------------

# Workflow Scorecards

Workflow evaluations can be converted into immutable workflow scorecards.

Scorecards represent a deterministic interpretation of workflow execution using a scoring policy.

```text
WorkflowRun
      │
      ▼
WorkflowEvaluation
      │
      ▼
WorkflowScorer
      │
      ▼
WorkflowScorecard
      ├── quality_score
      ├── reliability_score
      ├── latency_score
      ├── cost_score
      └── overall_score
```

```python
scorecard = WorkflowScorer().score(
    run=run,
    evaluation=evaluation,
)

scorecard.quality_score
scorecard.reliability_score
scorecard.latency_score
scorecard.cost_score
scorecard.overall_score
```

Workflow scorecards intentionally separate objective execution evidence from optimization policy.

Execution records facts.

Evaluations summarize those facts.

Scorecards interpret them according to a deterministic scoring policy.

This establishes the foundation for future capabilities including:

- workflow ranking;
- provider comparison;
- optimization loops;
- candidate selection;
- evolutionary search; and
- adaptive workflow generation.

------------------------------------------------------------------------

# Workflow Ranking

Workflow scorecards can be deterministically ranked.

Rankings establish an objective ordering of workflow executions according to a canonical comparison policy.

```text
WorkflowRun
      │
      ▼
WorkflowEvaluation
      │
      ▼
WorkflowScorecard
      │
      ▼
WorkflowRanker
      │
      ▼
WorkflowRanking
      ├── RankedWorkflow
      ├── RankedWorkflow
      ├── RankedWorkflow
      └── winner
```

```python
ranking = WorkflowRanker().rank(
    (
        scorecard_a,
        scorecard_b,
        scorecard_c,
    )
)

winner = ranking.winner
```

Workflow rankings compare workflow scorecards without modifying them.

The canonical ranking policy orders workflows by:

1. overall score;
2. quality;
3. reliability;
4. latency;
5. cost; and
6. original input order for exact ties.

Workflow ranking establishes the comparison layer required for future capabilities including:

- workflow selection;
- provider benchmarking;
- optimization tournaments;
- evolutionary search;
- candidate elimination; and
- adaptive workflow optimization.

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
