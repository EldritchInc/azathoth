# Workflows

`azathoth.workflows` provides the multi-step execution layer for Azathoth.

Workflows compose strategies into dependency-driven systems that can exchange values, execute conditionally, retry failures, record durable execution history, and participate in empirical experiments.

The workflow package is where individual executable strategies become larger systems.

## Purpose

A single strategy represents one executable behavior.

Real AI systems often require several behaviors coordinated together.

For example:

```text
Retrieve Context
      │
      ▼
Generate Answer
      │
      ▼
Validate Answer
      │
      ▼
Repair If Needed
```

Azathoth models these systems as workflows.

Workflows are designed so that:

- specifications remain independent of live provider objects;
- dependency graphs are validated before execution;
- workflow steps exchange explicit values;
- retries and failures are recorded durably;
- execution remains deterministic around inherently nondeterministic strategies; and
- completed workflows can be measured, scored, ranked, and optimized empirically.

## Workflow Lifecycle

The complete workflow lifecycle looks like this:

```text
WorkflowSpecification
        │
        ▼
generate_workflow_candidate()
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
WorkflowRunStatistics  WorkflowReliabilityMetrics
        │               │
        └───────┬───────┘
                │
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
       WorkflowRanking
                │
                ▼
 WorkflowExperimentRunner
                │
                ▼
 WorkflowExperimentResult
```

Each stage has a distinct responsibility.

## WorkflowSpecification

`WorkflowSpecification` describes a workflow without embedding runtime language model implementations.

A specification contains:

- workflow metadata; and
- one or more workflow step specifications.

```python
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowSpecification,
)

workflow = WorkflowSpecification(
    metadata=WorkflowMetadata(
        name="answer-and-validate",
        description="Generate an answer and validate the result.",
    ),
    steps=(
        first_step,
        second_step,
    ),
)
```

Specifications are immutable.

They represent the model-independent description of a workflow.

## WorkflowMetadata

Every workflow has stable metadata.

```python
from azathoth.workflows import WorkflowMetadata

metadata = WorkflowMetadata(
    name="research-workflow",
    description="Research and summarize a request.",
)
```

Metadata contains:

- a unique identifier;
- a name;
- a description; and
- a version.

This identity remains stable across specification, candidate generation, execution, and optimization.

## WorkflowStepSpecification

A `WorkflowStepSpecification` describes one step in a workflow.

A step may declare:

- a prompt strategy specification;
- dependencies;
- input bindings;
- output bindings;
- conditions;
- retry policy; and
- failure policy.

```text
WorkflowStepSpecification
├── specification
├── depends_on
├── inputs
├── outputs
├── conditions
├── retry_policy
└── failure_policy
```

The step specification remains model-independent.

Executable strategies are attached later during workflow candidate generation.

## Dependency Graph

Workflow steps may depend on earlier steps.

```text
A
├── B
└── C
    │
    ▼
    D
```

Dependencies are validated when a workflow specification is created.

Azathoth rejects:

- duplicate step identifiers;
- duplicate dependencies;
- self-dependencies;
- dependencies on unknown steps; and
- dependency cycles.

This ensures that an accepted workflow specification always represents a valid directed acyclic graph.

## Execution Layers

A valid workflow dependency graph can be grouped into execution layers.

For example:

```text
Layer 0
A

Layer 1
B   C

Layer 2
D
```

The workflow exposes these dependency-safe layers explicitly.

```python
layers = workflow.execution_layers()
```

Steps in the same layer depend only on steps from earlier layers.

The runner processes layers in dependency order while committing results in declared workflow order.

## Workflow Candidate Generation

A workflow specification is not directly executable.

It must first become a `WorkflowCandidate`.

```python
from azathoth.workflows import generate_workflow_candidate

candidate = generate_workflow_candidate(
    specification=workflow,
    catalog=catalog,
    registry=registry,
)
```

Generation resolves each model-independent prompt strategy specification into an executable prompt strategy.

```text
WorkflowSpecification
        │
        ▼
WorkflowStepSpecification
        │
        ▼
PromptStrategySpec
        │
        ▼
ModelCatalog
        +
LanguageModelRegistry
        │
        ▼
PromptStrategy
        │
        ▼
WorkflowCandidateStep
```

If any workflow step cannot produce an executable prompt candidate, generation fails with `WorkflowGenerationError`.

## WorkflowCandidate

`WorkflowCandidate` is the executable form of a workflow.

It contains:

- workflow metadata; and
- executable workflow candidate steps.

Each `WorkflowCandidateStep` contains a concrete `Strategy`.

```text
WorkflowCandidate
├── metadata
└── steps
    ├── executable strategy
    ├── dependencies
    ├── inputs
    ├── outputs
    ├── conditions
    ├── retry policy
    └── failure policy
```

Candidate topology is independently validated.

This protects runtime execution even when candidates are created directly rather than generated from specifications.

## Model Independence

The distinction between specification and candidate is fundamental.

```text
WorkflowSpecification
        │
        │ model independent
        ▼
Candidate Generation
        │
        ▼
WorkflowCandidate
        │
        │ executable
        ▼
Runtime Strategies
```

Specifications can be stored, compared, generated, and manipulated without carrying live provider implementations.

Candidates exist for execution.

## Workflow Values

Workflow steps can export structured values from their outputs.

`WorkflowValueBinding` declares:

- a value name; and
- an optional path into the strategy output.

```python
from azathoth.workflows import WorkflowValueBinding

binding = WorkflowValueBinding(
    name="answer",
)
```

A nested output can be resolved using a path:

```python
binding = WorkflowValueBinding(
    name="answer",
    path=(
        "result",
        "answer",
    ),
)
```

Paths may contain object keys and list indexes.

```text
Strategy Output
      │
      ▼
WorkflowValueBinding
      │
      ▼
WorkflowValue
```

Resolved values are immutable workflow artifacts.

## WorkflowValue

A produced `WorkflowValue` records:

- value name;
- JSON-compatible value; and
- producer step identifier.

```text
WorkflowValue
├── name
├── value
└── producer_step_id
```

This makes workflow data flow explicit and traceable.

## Input Bindings

Downstream steps consume workflow values using `WorkflowInputBinding`.

An input binding identifies:

- the local input name; and
- the upstream workflow value reference.

```text
Producer Step
      │
      ▼
WorkflowValue
      │
      ▼
WorkflowInputBinding
      │
      ▼
Consumer Step Context
```

Before executing a downstream step, the runner resolves each binding and appends a `workflow.input.bound` event to the step-local context.

This keeps workflow data propagation compatible with Azathoth's event-backed context model.

## Value Reference Validation

Workflow specifications validate value references before execution.

An input may only reference:

- a step in the same workflow;
- an output declared by that step; and
- a value produced by an upstream dependency.

This prevents invalid workflow data flow from reaching runtime execution.

## Conditions

Workflow steps may execute conditionally.

A `WorkflowCondition` compares an upstream workflow value with an expected value.

```text
WorkflowValue
      │
      ▼
WorkflowCondition
      │
      ├── matches → execute
      │
      └── fails   → skip
```

Current condition operators include:

- equal;
- not equal;
- greater than;
- greater than or equal;
- less than; and
- less than or equal.

Ordering comparisons require numeric values.

Invalid numeric comparisons raise `WorkflowConditionEvaluationError`.

## Conditional Execution

All conditions attached to a workflow step must be satisfied before that step executes.

If a condition does not match, the step is recorded as:

```text
SKIPPED
```

Skipped steps:

- do not execute a strategy;
- record no execution attempts; and
- produce no workflow values.

Skipping is durable execution evidence, not an invisible control-flow decision.

## Retry Policies

Workflow steps can declare retry behavior using `WorkflowRetryPolicy`.

```python
from azathoth.workflows import WorkflowRetryPolicy

retry_policy = WorkflowRetryPolicy(
    max_attempts=3,
    initial_delay_seconds=1.0,
    backoff_multiplier=2.0,
    maximum_delay_seconds=10.0,
)
```

Retry policies support:

- maximum attempts;
- initial retry delay;
- backoff multiplier; and
- maximum delay.

```text
Attempt 1
   │ failure
   ▼
Attempt 2
   │ failure
   ▼
Attempt 3
   │
   ▼
Success or Final Failure
```

Retry calculations are deterministic.

## Workflow Step Attempts

Every attempted step execution is recorded as a `WorkflowStepAttempt`.

An attempt records:

- attempt number;
- start time;
- completion time; and
- exactly one outcome.

The outcome is either:

```text
ExecutionResult
```

or:

```text
WorkflowStepFailure
```

Never both.

## WorkflowStepFailure

A failed attempt records durable failure information.

```text
WorkflowStepFailure
├── exception_type
└── message
```

The original exception controls runtime failure behavior.

The durable failure model preserves enough information for later inspection, statistics, and optimization.

## Failure Policies

A workflow step can decide what happens after its retries are exhausted.

Current failure policies are:

- `FAIL_WORKFLOW`
- `CONTINUE`
- `SKIP_DEPENDENTS`

### FAIL_WORKFLOW

The workflow stops and the original exception is raised.

### CONTINUE

The failed step is recorded, but independent later execution may continue.

### SKIP_DEPENDENTS

The failed step is recorded and downstream dependent steps are skipped transitively.

```text
A fails
  │
  └── SKIP_DEPENDENTS
          │
          ▼
          B skipped
          │
          ▼
          C skipped
```

This behavior is explicit and preserved in workflow execution history.

## WorkflowRunner

`WorkflowRunner` executes a `WorkflowCandidate` against an initial `Context`.

```python
from azathoth.workflows import WorkflowRunner

run = await WorkflowRunner().run(
    workflow=candidate,
    context=context,
)
```

The runner coordinates:

- dependency layers;
- condition evaluation;
- workflow input resolution;
- retry behavior;
- failure policies;
- strategy execution;
- execution-context merging;
- workflow value production; and
- durable step recording.

The runner does not evaluate correctness or rank workflows.

## Provider-backed Workflow Execution

Workflow execution remains provider neutral.

```text
WorkflowSpecification
          │
          ▼
generate_workflow_candidate()
          │
          ▼
WorkflowCandidate
          │
          ▼
WorkflowRunner
          │
          ▼
PromptStrategy
          │
          ▼
LanguageModel
          │
          ▼
ModelResponse
```

The workflow layer never communicates directly with provider-specific APIs.

Language model execution is delegated through the provider abstraction, allowing
the same workflow to execute against deterministic models, OpenRouter, or future
providers without changing workflow definitions.

## Layer Execution

The runner processes dependency-safe layers.

All steps in one layer receive the same layer-start context.

Their execution results are then committed in declared workflow order.

```text
Layer Context
    │
    ├── Step B
    └── Step C
          │
          ▼
Deterministic Commit Order
```

This prevents sibling steps from accidentally observing each other's execution events within the same dependency layer.

## Context Merging

Each workflow step executes with a step-local context.

After successful execution, only events produced during that execution are merged back into the shared workflow context.

```text
Shared Context
      │
      ▼
Step Context
      │
      ▼
Strategy Execution
      │
      ▼
Produced Events
      │
      ▼
Shared Context
```

The runner validates that strategy execution preserved the expected initial step context before merging events.

## Workflow Step Status

Every workflow step run has one of three statuses:

- `EXECUTED`
- `FAILED`
- `SKIPPED`

These statuses have strict invariants.

### EXECUTED

Must contain:

- a successful execution result;
- at least one attempt; and
- a final successful attempt matching the execution result.

### FAILED

Must contain:

- no successful execution result;
- at least one attempt;
- a final failed attempt; and
- no produced values.

### SKIPPED

Must contain:

- no execution result;
- no attempts; and
- no produced values.

These invariants make workflow execution history self-consistent.

## WorkflowRun

A completed workflow produces an immutable `WorkflowRun`.

```text
WorkflowRun
├── workflow metadata
├── step runs
├── initial context
├── final context
├── started_at
└── completed_at
```

A workflow run is the durable record of what happened during execution.

## Workflow Values From a Run

A workflow run exposes all produced workflow values.

```python
values = run.values
```

Values can also be queried by name:

```python
answers = run.values_named("answer")
```

or by producer step:

```python
values = run.values_from(step_id)
```

This provides structured access to workflow outputs without reconstructing execution state.

## Workflow Statistics

Every workflow run exposes derived `WorkflowRunStatistics`.

```python
statistics = run.statistics
```

Statistics include:

- total steps;
- executed steps;
- failed steps;
- skipped steps;
- total attempts;
- successful attempts;
- failed attempts;
- retry count; and
- workflow duration.

```text
WorkflowRun
    │
    ▼
WorkflowRunStatistics
```

Statistics are derived from durable execution history rather than stored separately.

## Workflow Reliability

A workflow run also exposes normalized `WorkflowReliabilityMetrics`.

```python
reliability = run.reliability
```

Current reliability dimensions include:

- completion rate;
- first-attempt success rate;
- retry rate; and
- failure rate.

All reliability metrics are normalized between:

```text
0.0
and
1.0
```

This allows workflows of different sizes to be compared consistently.

## Workflow Success

A workflow succeeds when it contains no failed steps.

```python
if run.succeeded:
    ...
```

A workflow may contain skipped steps and still be considered successful.

This distinction is important because conditional branches may legitimately skip execution.

## Workflow Scorecards

Workflow execution and output evaluation can be combined into a normalized `WorkflowScorecard`.

```text
EvaluationResult
      │
      ├── Quality
      │
WorkflowRun
      ├── Reliability
      ├── Latency
      └── Cost
      │
      ▼
WorkflowScorer
      │
      ▼
WorkflowScorecard
```

A scorecard contains:

- quality score;
- reliability score;
- latency score;
- cost score;
- overall score; and
- rationale.

All scores are normalized between `0.0` and `1.0`.

## WorkflowScoringPolicy

Latency and cost are only meaningful relative to an objective.

`WorkflowScoringPolicy` provides explicit normalization targets.

```python
from azathoth.workflows import WorkflowScoringPolicy

policy = WorkflowScoringPolicy(
    target_latency_seconds=5.0,
    target_cost_usd=0.01,
)
```

The scoring policy currently establishes canonical targets rather than learned optimization weights.

## WorkflowScorer

`WorkflowScorer` combines output evaluation with execution evidence.

```python
from azathoth.workflows import WorkflowScorer

scorecard = WorkflowScorer(
    policy=policy,
).score(
    run=run,
    evaluation=evaluation,
)
```

Scoring remains separate from evaluation.

Evaluation asks:

> Was the result correct?

Scoring asks:

> Given correctness, reliability, latency, and cost, how desirable was this workflow execution?

## Workflow Ranking

Several workflow scorecards can be compared using `WorkflowRanker`.

```text
WorkflowScorecard A
WorkflowScorecard B
WorkflowScorecard C
        │
        ▼
WorkflowRanker
        │
        ▼
WorkflowRanking
```

Ranking is deterministic.

The canonical ordering compares:

1. overall score;
2. quality score;
3. reliability score;
4. latency score;
5. cost score; and
6. original input order for exact ties.

## RankedWorkflow

Each ranking entry is represented by `RankedWorkflow`.

```text
RankedWorkflow
├── rank
└── scorecard
```

Ranks are consecutive and begin at one.

## WorkflowRanking

`WorkflowRanking` contains the complete ordered comparison.

```python
ranking = WorkflowRanker().rank(scorecards)

winner = ranking.winner
```

The winner is simply the scorecard at rank one.

Ranking does not mutate scorecards or introduce new execution evidence.

## Workflow Experiments

`WorkflowExperimentRunner` orchestrates a deterministic tournament over workflow candidates.

```text
Workflow Candidates
        │
        ▼
WorkflowExperimentRunner
        │
        ├── WorkflowRunner
        ├── Evaluator
        ├── WorkflowScorer
        └── WorkflowRanker
        │
        ▼
WorkflowExperimentResult
```

For each candidate, an experiment:

1. executes the workflow;
2. extracts the final successful workflow output;
3. evaluates that output;
4. scores the workflow execution; and
5. ranks all resulting scorecards.

## WorkflowExperimentResult

An experiment result contains:

- workflow scorecards; and
- the final workflow ranking.

It also exposes the winner directly.

```python
result = await experiment_runner.run(
    workflows=candidates,
    context=context,
    evaluator=evaluator,
    expected_outcome=expected,
)

winner = result.winner
```

Experiment results are immutable.

## Deterministic and Live Testing

Workflow execution is verified at two levels.

Deterministic tests execute workflows using mocked language model
implementations and mocked HTTP transports.

```text
Workflow
    │
    ▼
Mock Language Model
```

Live workflow verification is available through an explicit opt-in smoke test.

```text
Workflow
    │
    ▼
OpenRouter
```

Normal development and continuous integration remain deterministic and consume
no provider credits.

Live execution is enabled only by explicitly setting:

```text
AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1
```

## Experiments Are Not Optimization

Workflow experiments compare candidate populations.

They do not generate new candidates.

```text
Experiment
   │
   ▼
Evidence
```

Optimization begins only after experiment evidence exists.

This boundary keeps empirical measurement separate from candidate transformation.

## Relationship to Optimization

The workflow package owns:

- workflow specification;
- candidate generation;
- workflow execution;
- execution evidence;
- scoring;
- ranking; and
- experiments.

The optimization package owns:

- producing future candidate generations;
- optimization results;
- replay optimization; and
- multi-generation optimization sessions.

```text
azathoth.workflows
        │
        ▼
WorkflowExperimentResult
        │
        ▼
azathoth.optimization
        │
        ▼
Next Candidate Generation
```

This boundary prevents optimization algorithms from leaking into workflow execution.

## Design Principles

The workflow domain is intentionally:

- immutable where execution artifacts are concerned;
- explicit about dependencies;
- explicit about data flow;
- model-independent at specification time;
- deterministic around strategy behavior;
- traceable across retries and failures;
- independently measurable;
- empirically comparable; and
- independent of optimization algorithms.

Workflows define and execute candidate systems.

They do not decide how future generations should be produced.

## Complete Workflow Flow

The complete current workflow pipeline is:

```text
WorkflowSpecification
        │
        ▼
generate_workflow_candidate()
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
Statistics          Reliability
        │               │
        └───────┬───────┘
                │
EvaluationResult
        │       │
        └───┬───┘
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
    WorkflowRanking
            │
            ▼
WorkflowExperimentRunner
            │
            ▼
WorkflowExperimentResult
            │
            ▼
    Optimization Domain
```

## Relationship to Other Packages

[`azathoth.context`](../context/README.md) provides event-backed execution state and workflow input propagation.

[`azathoth.strategies`](../strategies/README.md) defines the executable behaviors composed into workflow steps.

[`azathoth.execution`](../execution/README.md) executes individual workflow step strategies and records execution results.

[`azathoth.evaluation`](../evaluation/README.md) judges workflow outputs before scorecards are produced.

[`azathoth.prompting`](../prompting/README.md) provides model-independent prompt strategy specifications used by workflow steps.

[`azathoth.providers`](../providers/README.md) supplies model discovery and runtime model implementations during candidate generation.

[`azathoth.optimization`](../optimization/README.md) consumes workflow experiment evidence and produces future candidate generations.

See the [project README](../../../README.md) for the complete Azathoth architecture.