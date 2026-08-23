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

## Workflow Persistence

Workflow specifications may be stored outside the Azathoth source tree.

`WorkflowRepository` provides a storage-neutral persistence boundary.

Current repository implementations include:

- in-memory persistence; and
- SQLite persistence.

```text
WorkflowSpecification
        │
        ▼
WorkflowRepository
        │
        ├── InMemoryWorkflowRepository
        │
        └── SQLiteWorkflowRepository
```

Repositories persist `WorkflowSpecification`, not `WorkflowCandidate`.

A workflow specification is the durable, model-independent recipe for a
workflow.

A workflow candidate contains resolved runtime strategies and remains an
executable runtime artifact.

## Workflow Catalogs

`WorkflowCatalogLoader` reconstructs an immutable `WorkflowCatalog` from
repository state.

```text
WorkflowRepository
        │
        ▼
WorkflowCatalogLoader
        │
        ▼
WorkflowCatalog
        │
        ▼
WorkflowSpecification
```

The catalog preserves repository order and supports deterministic lookup by
workflow identifier.

Persistence remains below candidate generation.

```text
SQLite
  │
  ▼
WorkflowRepository
  │
  ▼
WorkflowCatalogLoader
  │
  ▼
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
```

Candidate generation does not know whether a specification originated from
SQLite, memory, application configuration, or another repository
implementation.

## Workflow JSON Documents

Durable workflow specifications can be represented as portable JSON documents.

```text
WorkflowSpecification
        │
        ▼
encode_workflow_document()
        │
        ▼
JSON
        │
        ▼
decode_workflow_document()
        │
        ▼
WorkflowSpecification
```

`encode_workflow_document()` produces readable canonical JSON for a complete
workflow specification.

`decode_workflow_document()` validates a JSON document through the existing
workflow domain model.

Invalid JSON or invalid workflow configuration raises:

```text
WorkflowDocumentError
```

Workflow documents use the same durable representation as workflow
persistence. They do not introduce a separate interchange model.

### Canonical Example

A complete importable document is available at:

```text
examples/workflows/simple-prompt.json
```

The test suite verifies that the checked-in file exactly matches canonical
serialization of its expected `WorkflowSpecification`.

This means the example is kept synchronized with the actual workflow document
format.

### Durable Only

Workflow documents contain specifications rather than runtime candidates.

```text
JSON document
      │
      ▼
WorkflowSpecification
```

They do not serialize:

- concrete language-model implementations;
- runtime model bindings;
- resolved tool implementations;
- workflow candidates; or
- workflow runs.

Executable dependencies are attached later through the existing candidate
generation path.

## Reconstructed Execution

Persisted workflow specifications can be reconstructed and executed using the
same runtime infrastructure as directly constructed specifications.

A persisted workflow may reference persisted tool capabilities and declare
model requirements that are resolved against persisted model metadata.

```text
Persisted WorkflowSpecification
              +
Persisted Tool Definitions / Implementations
              +
Persisted ModelMetadata
              │
              ▼
     Reconstructed Catalogs
              │
              ▼
       Runtime Assembly
              │
              ▼
      Candidate Generation
              │
              ▼
        WorkflowRunner
```

Workflow persistence introduces no separate execution path.

Model-backed steps continue to resolve through `ModelCatalog` and
`LanguageModelRegistry`.

Tool-backed steps continue to resolve through the tool subsystem.

Reconstructed workflows retain their:

- metadata;
- step specifications;
- dependency graph;
- input bindings;
- output bindings;
- conditions;
- retry policies; and
- failure policies.

### Runtime Composition

Applications may compose reconstructed workflow, model, and tool catalogs
through `AzathothRuntime`.

```text
WorkflowCatalog
ModelCatalog
ToolCatalog
ToolImplementationCatalog
        +
LanguageModelRegistry
        │
        ▼
AzathothRuntime
```

The runtime exposes workflow candidate generation by stable workflow identity.

```python
candidate = runtime.generate_workflow_candidate(
    workflow_id,
)
```

This delegates to the existing `generate_workflow_candidate()` function.

Prompt-backed and tool-backed step resolution therefore follow the same
candidate-generation path whether the catalogs were constructed directly or
reconstructed from persistent storage.

`AzathothRuntime` does not execute workflows.

The resulting `WorkflowCandidate` continues to execute through
`WorkflowRunner`.

### Durable Model Resolution

Both the workflow's model requirements and the configured model universe may
survive process restart.

```text
WorkflowRepository
       │
       ▼
WorkflowCatalogLoader
       │
       ▼
WorkflowSpecification
       │
       └── ModelRequirements
                 +
ModelRepository
       │
       ▼
ModelCatalogLoader
       │
       ▼
ModelCatalog
                 │
                 ▼
       Candidate Generation
```

Concrete provider implementations remain runtime dependencies and are attached
after model metadata is reconstructed.

Different prompt-backed steps may still resolve different models after restart.

```text
Step A requirements → model A
Step B requirements → model C
Step C requirements → model B
```

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

- a prompt-backed or tool-backed executable specification;
- dependencies;
- input bindings;
- output bindings;
- conditions;
- retry policy; and
- failure policy.

```text
WorkflowStepSpecification
├── specification
│   ├── PromptStrategySpec
│   └── ToolStepSpecification
├── depends_on
├── inputs
├── outputs
├── conditions
├── retry_policy
└── failure_policy
```

The outer workflow step owns workflow behavior.

The nested specification describes the capability that must become executable.

Prompt-backed steps declare model requirements through `PromptStrategySpec`.

Tool-backed steps declare durable capability requirements through
`ToolStepSpecification`.

```text
ToolStepSpecification
        │
        ▼
ToolRequirement
```

Neither specification embeds a live runtime implementation.

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
    catalog=model_catalog,
    registry=model_registry,
    tool_resolver=tool_resolver,
    tool_implementation_resolver=tool_implementation_resolver,
)
```

Candidate generation resolves each step according to its specification type.

Prompt-backed steps use the provider subsystem:

```text
PromptStrategySpec
        │
        ▼
ModelCatalog
        +
LanguageModelRegistry
        │
        ▼
PromptStrategy
```

Tool-backed steps use the tool subsystem:

```text
ToolStepSpecification
        │
        ▼
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
ToolStrategy
```

Both become ordinary executable workflow candidate steps.

```text
WorkflowSpecification
        │
        ▼
Candidate Generation
       / \
      /   \
     ▼     ▼
 Prompt   Tool
Strategy Strategy
      \   /
       \ /
        ▼
WorkflowCandidate
```

Tool resolution introduces no workflow optimization or implementation ranking
policy.

If a required executable strategy cannot be produced, candidate generation
fails with `WorkflowGenerationError`.

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

### Per-Step Model Resolution

Prompt-backed workflow steps resolve models independently.

Each `PromptStrategySpec` contains its own `ModelRequirements`.

```text
WorkflowSpecification
│
├── Prompt Step A
│   └── ModelRequirements A
│
├── Prompt Step B
│   └── ModelRequirements B
│
└── Prompt Step C
    └── ModelRequirements C
```

Candidate generation performs model discovery separately for each prompt-backed
step.

Different steps in one workflow may therefore resolve to different concrete
language models.

```text
Step A requirements
        │
        ▼
     Model A

Step B requirements
        │
        ▼
     Model C

Step C requirements
        │
        ▼
     Model B
```

The concrete model choice is recorded in the generated prompt strategy's
`ModelBinding`.

The workflow specification itself remains model-independent.

### Heterogeneous Provider Execution

A workflow does not have one global language model.

Multiple prompt-backed steps may use:

- different models from one provider;
- models from different providers; or
- any mixture represented by the configured catalog and executable registry.

For example:

```text
Workflow
│
├── inexpensive classification
│       └── OpenRouter model A
│
├── structured extraction
│       └── OpenRouter model B
│
└── later prompt step
        └── another registered model
```

Each step retains its own provider-neutral execution metrics, including model,
token usage, latency, and estimated cost.

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

## Tool Input Binding

Tool-backed steps consume workflow inputs through the same event-backed
mechanism used by other context-driven strategies.

Before a downstream step executes, `WorkflowRunner` resolves its
`WorkflowInputBinding` objects and appends step-local:

```text
workflow.input.bound
```

events.

`ToolStrategy` converts those events into the structured input mapping supplied
to its `ToolExecutor`.

```text
Upstream WorkflowValue
          │
          ▼
 WorkflowInputBinding
          │
          ▼
 workflow.input.bound
          │
          ▼
     ToolStrategy
          │
          ▼
      ToolExecutor
```

Workflow-bound input events remain local to the consuming step.

They are not committed into the workflow's shared final context merely because
a step consumed them.

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

## Tool-Driven Conditional Routing

Tool-backed steps produce normal workflow values.

Those values can therefore participate in existing workflow conditions without
any tool-specific routing behavior.

```text
Persisted Tool
      │
      ▼
ToolStrategy
      │
      ▼
{"word_count": 4}
      │
      ▼
WorkflowValue
      │
      ▼
WorkflowCondition
     / \
    /   \
   ▼     ▼
execute skip
```

For example, a numeric tool output can drive the existing ordering condition
operators:

```text
word_count >= 4
```

The condition system does not know or care whether its source value originated
from a prompt-backed strategy, a deterministic tool, or another strategy.

Routing remains a workflow concern.

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

## Workflow Run Persistence

`WorkflowRun` is the durable record of one completed workflow execution.

Each run has its own stable identifier.

```text
Workflow
   │
   ▼
WorkflowRunner
   │
   ▼
WorkflowRun
├── id
├── workflow metadata
├── step runs
├── execution attempts
├── workflow values
├── initial context
├── final context
└── timestamps
```

The workflow identifier identifies the workflow definition.

The run identifier identifies one particular execution of that workflow.

`WorkflowRunRepository` provides a storage-neutral persistence boundary.

Current implementations include:

- `InMemoryWorkflowRunRepository`; and
- `SQLiteWorkflowRunRepository`.

```text
WorkflowRun
    │
    ▼
WorkflowRunRepository
    │
    ├── InMemoryWorkflowRunRepository
    │
    └── SQLiteWorkflowRunRepository
```

Workflow run evidence is append-only.

Persisting another run with the same run identifier is rejected.

## Reconstructed Run Evidence

SQLite persistence serializes the complete immutable `WorkflowRun`.

```text
WorkflowRun
    │
    ▼
SQLite
    │
    │ process restart
    ▼
WorkflowRun
```

Reconstructed runs preserve:

- workflow identity;
- step status;
- strategy execution results;
- execution attempts;
- failures;
- workflow values;
- contexts; and
- timestamps.

Statistics and reliability remain derived from the reconstructed raw evidence
rather than being separately persisted.

```text
WorkflowRun
    │
    ├── WorkflowRunStatistics
    └── WorkflowReliabilityMetrics
```

This keeps the persisted execution record canonical.

## Workflow Run Evaluations

Evaluator judgments can be durably associated with completed workflow runs.

`EvaluationResult` remains independent of workflow execution.

The workflow layer represents the relationship using
`WorkflowRunEvaluation`.

```text
WorkflowRunEvaluation
├── run_id
├── evaluation
└── evaluated_at
```

The embedded `EvaluationResult` retains the complete evaluator judgment,
including:

- evaluator name and version;
- score;
- threshold;
- status;
- reason; and
- structured evidence.

The evaluation's existing identifier is also the durable identity of the
`WorkflowRunEvaluation`.

```text
WorkflowRunEvaluation.id
          │
          ▼
EvaluationResult.id
```

This avoids introducing two identities for one evaluator judgment.

### Evaluation Persistence

`WorkflowRunEvaluationRepository` provides the storage-neutral persistence
boundary.

Current implementations include:

- `InMemoryWorkflowRunEvaluationRepository`; and
- `SQLiteWorkflowRunEvaluationRepository`.

```text
WorkflowRun
    │
    │ run_id
    ▼
WorkflowRunEvaluation
    │
    ▼
WorkflowRunEvaluationRepository
    │
    ├── InMemoryWorkflowRunEvaluationRepository
    └── SQLiteWorkflowRunEvaluationRepository
```

Run evaluations are append-only.

Multiple evaluations may reference the same workflow run.

```text
WorkflowRun
    │
    ├── Evaluation A
    ├── Evaluation B
    └── Evaluation C
```

This allows independent evaluators to judge different properties of the same
execution without replacing one another.

Persisted evaluations can be reconstructed by evaluation identifier or queried
by workflow run identifier.

## Workflow Run Feedback

Judgment about a completed run is stored separately from the run itself.

`WorkflowRunFeedback` records one human or application judgment.

```text
WorkflowRunFeedback
├── id
├── run_id
├── disposition
├── reason
├── corrected_output
└── created_at
```

A disposition is either:

- `good`; or
- `bad`.

Bad feedback requires a reason.

A corrected output may optionally record what the caller expected instead.

```python
feedback = WorkflowRunFeedback(
    run_id=run.id,
    disposition=WorkflowRunFeedbackDisposition.BAD,
    reason="The classification was incorrect.",
    corrected_output="negative",
)
```

Feedback never modifies the original `WorkflowRun`.

```text
WorkflowRun
actual output = "positive"
        │
        │ run_id
        ▼
WorkflowRunFeedback
disposition = "bad"
reason = "The classification was incorrect."
corrected_output = "negative"
```

The recorded output remains `"positive"` because that is what actually
happened.

## Feedback Persistence

`WorkflowRunFeedbackRepository` provides the persistence boundary for these
later judgments.

Current implementations include:

- `InMemoryWorkflowRunFeedbackRepository`; and
- `SQLiteWorkflowRunFeedbackRepository`.

```text
WorkflowRun
    │
    │ id
    ▼
WorkflowRunFeedback
    │
    ▼
WorkflowRunFeedbackRepository
```

Feedback records are append-only.

Multiple feedback records may reference the same workflow run.

This preserves judgment history instead of treating feedback as one mutable
field on the execution record.

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

## Workflow Benchmarks

Workflow benchmarks evaluate workflow candidates across representative
workloads.

```text
Benchmark Dataset
        │
        ▼
Workflow Candidate
        │
        ▼
Workflow Runner
        │
        ▼
Workflow Evaluation
        │
        ▼
Workflow Scorecard
```

Benchmark datasets reuse existing workflow execution.

They introduce no provider-specific behavior and no alternative evaluation
pipeline.

Each benchmark case executes independently using the same workflow
infrastructure used elsewhere throughout Azathoth.

### Durable Benchmark Execution

Benchmark datasets may be reconstructed from persistent storage before
execution.

```text
SQLiteBenchmarkRepository
          │
          ▼
BenchmarkCatalogLoader
          │
          ▼
BenchmarkDataset
          │
          ▼
WorkflowBenchmarkRunner
```

The benchmark runner does not distinguish between directly constructed and
reconstructed datasets.

For each case, the runner:

```text
BenchmarkCase
      │
      ▼
candidate_factory(case)
      │
      ▼
WorkflowCandidate
      │
      ▼
WorkflowRunner
      │
      ▼
workflow output
      │
      +
ExpectedOutcome
      │
      ▼
Evaluator
```

This allows a benchmark workload persisted today to be reconstructed and run
later using the normal workflow execution path.

Dataset identity and benchmark case identity are retained in benchmark
execution evidence.

Durable benchmark definitions remain separate from the runtime workflow
candidates used to execute them.

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

## Benchmark Ranking

Workflow benchmarks compare multiple workflow candidates using the existing
workflow scoring and ranking system.

```text
Workflow Benchmark
        │
        ▼
Workflow Scorecards
        │
        ▼
Workflow Ranker
        │
        ▼
Ranked Candidates
```

Benchmark execution produces evidence.

Workflow scoring interprets that evidence.

Workflow ranking determines candidate ordering.

Benchmark infrastructure intentionally does not define its own optimization
policy.

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

## Observation Versus Judgment

Azathoth distinguishes raw execution evidence from judgments about execution.

```text
                    WorkflowRun
                   "What happened?"
                    /         \
                   /           \
                  ▼             ▼
 WorkflowRunEvaluation     WorkflowRunFeedback
 "Machine judgment"        "Human/app judgment"
          │                       │
          ▼                       ▼
  EvaluationResult            good / bad
```

These artifacts are independent.

An evaluator may fail a run while a human or application considers the same
result acceptable.

Conversely, an evaluator may pass a result that later receives bad feedback.

Neither case changes the original workflow execution record.

```text
WorkflowRun
    │
    ├── evaluation: FAILED
    └── feedback: GOOD
```

The disagreement itself is preserved as evidence.

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

## Durable Workflow Experiment Records

`WorkflowExperimentResult` is useful as immediate experiment output, but durable
experiment history also needs provenance linking derived scorecards back to the
executions and evaluator judgments that produced them.

`WorkflowExperimentRecord` provides that durable representation.

```text
WorkflowExperimentRecord
├── id
├── observations
├── ranking
└── recorded_at
```

Each observation records:

```text
WorkflowExperimentObservation
├── workflow
├── run_id
├── evaluation_id
└── scorecard
```

The record references persisted execution and evaluation evidence rather than
embedding duplicate copies.

```text
WorkflowExperimentObservation
        │
        ├── run_id ─────────► WorkflowRun
        │
        └── evaluation_id ──► WorkflowRunEvaluation
```

### Experiment Ranking

Durable experiment rankings use workflow-run identity.

```text
WorkflowExperimentRecord
        │
        ▼
ranking
├── best run
├── second run
└── remaining runs
```

Every observed run must appear exactly once in the ranking.

The first ranked observation is exposed as the experiment winner.

### Experiment Persistence

`WorkflowExperimentRepository` provides the storage-neutral persistence
boundary.

Current implementations include:

- `InMemoryWorkflowExperimentRepository`; and
- `SQLiteWorkflowExperimentRepository`.

```text
WorkflowExperimentRecord
        │
        ▼
WorkflowExperimentRepository
       / \
      /   \
     ▼     ▼
 memory  SQLite
```

Experiment records are append-only.

SQLite also stores queryable workflow, run, and evaluation identities so
experiment history can be discovered without deserializing every record.

### Durable Experiment Provenance

A reconstructed experiment can be followed back to its exact source evidence.

```text
WorkflowExperimentRecord
        │
        ├── run_id
        │      ▼
        │  WorkflowRunRepository
        │      ▼
        │  WorkflowRun
        │
        └── evaluation_id
               ▼
       WorkflowRunEvaluationRepository
               ▼
       EvaluationResult
```

Scorecards and rankings remain historical derived evidence.

They do not replace the raw execution or evaluator records from which they were
produced.

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

Persisting experiment provenance does not change this boundary.

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