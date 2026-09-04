# Workflows

`azathoth.workflows` defines the durable, executable, empirical, and production
lifecycle of an Azathoth workflow.

A workflow moves through distinct representations rather than allowing one
object to accumulate configuration, runtime state, experimental evidence, and
production authority.

```text
WorkflowSpecification
        │
        │ generation
        ▼
WorkflowCandidate
        │
        │ execution
        ▼
WorkflowRun
        │
        ├──────────────► evaluation / feedback / experiments
        │
        └──────────────► optimization
                                │
                                ▼
                         WorkflowCandidate
                                │
                                │ explicit promotion
                                ▼
                     WorkflowProductionState
                                │
                                │ production invocation
                                ▼
                           WorkflowRun
```

The separation between these representations is intentional.

## Workflow Specification

`WorkflowSpecification` is durable workflow intent.

It contains workflow metadata and an ordered collection of
`WorkflowStepSpecification` values.

A specification describes what the workflow is allowed and expected to do. It
is not itself an executable runtime instance and does not contain empirical
execution state.

Workflow specifications may be persisted through `WorkflowRepository`
implementations, including:

- `InMemoryWorkflowRepository`
- `SQLiteWorkflowRepository`

They can also be serialized and reconstructed through:

- `encode_workflow_document`
- `decode_workflow_document`

## Workflow Steps

A workflow is composed from `WorkflowStepSpecification` values.

Steps may be prompt-backed or tool-backed.

Prompt-backed steps carry prompting strategy configuration and model-selection
intent.

Tool-backed steps reference durable tool capability rather than embedding
process-local executable implementations.

Steps can additionally describe:

- dependencies
- input bindings
- output bindings
- conditions
- retry policy
- failure policy

These properties form durable workflow topology and policy.

They are distinct from execution evidence.

## Candidate Generation

`WorkflowCandidate` is an executable realization of a workflow specification.

Candidate generation resolves durable workflow intent against the process-local
runtime environment.

```text
WorkflowSpecification
        +
ModelCatalog
ModelPortfolio
LanguageModelRegistry
ToolResolver
ToolImplementationResolver
        │
        ▼
WorkflowCandidate
```

`generate_workflow_candidate` performs this generation.

Candidate generation can fail explicitly with `WorkflowGenerationError` when
durable intent cannot be resolved into an executable candidate.

A candidate retains workflow identity while binding individual workflow steps
to executable strategies.

`WorkflowCandidateSignature` provides deterministic executable candidate
identity for empirical comparison.

A candidate is not production state.

It represents one executable possibility.

## Workflow Execution

`WorkflowRunner` executes a `WorkflowCandidate`.

Execution produces a `WorkflowRun`.

```text
WorkflowCandidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

`WorkflowRun` is immutable empirical evidence of what happened.

It contains `WorkflowStepRun` values describing the observed execution of each
step.

Step execution status is represented by `WorkflowStepStatus`.

Retries and terminal failures are represented through:

- `WorkflowStepAttempt`
- `WorkflowStepFailure`

Execution evidence is distinct from workflow configuration.

Running a workflow does not modify the workflow specification to reflect what
occurred.

## Values and Data Flow

Workflow data flow is explicit.

The workflow value model includes:

- `WorkflowInputBinding`
- `WorkflowValueBinding`
- `WorkflowValueReference`
- `WorkflowValue`

Bindings describe declared data flow between workflow inputs, workflow steps,
and step outputs.

Invalid value resolution fails explicitly with
`WorkflowValueResolutionError`.

## Conditions, Retries, and Failure Policy

Workflow control flow remains part of durable workflow intent.

Conditional execution is represented by:

- `WorkflowCondition`
- `WorkflowConditionOperator`

Condition evaluation failures are represented by
`WorkflowConditionEvaluationError`.

Retry behavior is represented by `WorkflowRetryPolicy`.

Failure handling is represented by `WorkflowFailurePolicy`.

These policies affect execution but remain separate from the resulting
`WorkflowRun` evidence.

## Evaluation and Evidence

Workflow execution evidence can be evaluated independently of execution.

The workflow package includes:

- `WorkflowEvaluation`
- `WorkflowRunEvaluation`
- `WorkflowScorecard`
- `WorkflowReliabilityMetrics`
- `WorkflowRunStatistics`

Run evaluations can be persisted through
`WorkflowRunEvaluationRepository` implementations.

This allows execution and judgment to remain separate concerns.

```text
WorkflowRun
     │
     ▼
evaluation
     │
     ▼
WorkflowRunEvaluation
```

## Feedback

Observed workflow runs may receive explicit feedback through
`WorkflowRunFeedback`.

Feedback disposition is represented by `WorkflowRunFeedbackDisposition`.

Feedback persistence is provided by `WorkflowRunFeedbackRepository`
implementations.

Feedback is evidence associated with execution.

It does not silently mutate durable workflow configuration.

## Experiments

Experiments compare executable workflow candidates using empirical execution.

`WorkflowExperimentRunner` executes candidates and produces experiment
evidence.

The experiment model includes:

- `WorkflowExperimentEvidence`
- `WorkflowExperimentResult`
- `WorkflowExperimentObservation`
- `WorkflowExperimentRecord`

Experiment records can be persisted through `WorkflowExperimentRepository`
implementations.

Experiment results identify empirical winners without automatically changing
production state.

Selection and deployment remain separate operations.

## Scoring and Ranking

Workflow evidence can be converted into scorecards through:

- `WorkflowScorer`
- `WorkflowScoringPolicy`

Candidates can be ordered through:

- `WorkflowRanker`
- `WorkflowRanking`
- `RankedWorkflow`

Scoring and ranking describe empirical preference.

They do not confer production authority.

## Benchmarking

The workflow package also provides deterministic benchmark infrastructure for
comparing workflow candidates across benchmark cases.

The benchmark surface includes:

- `WorkflowBenchmarkRunner`
- `WorkflowBenchmarkScorer`
- `WorkflowBenchmarkRanker`
- `WorkflowBenchmarkComparator`
- `WorkflowBenchmarkResult`
- `WorkflowBenchmarkRanking`
- `WorkflowBenchmarkComparison`

Benchmark results remain evidence.

They do not mutate configured or production workflow state.

## Production Promotion

Production promotion is explicit.

`promote_workflow_candidate` converts one explicitly selected executable
candidate into durable production intent.

```text
WorkflowSpecification
        +
WorkflowCandidate
        │
        ▼
materialize_workflow_candidate
        │
        ▼
WorkflowProductionState
```

Prompt-backed candidate model bindings are materialized as exact
`FixedModelSelection` values.

This prevents production behavior from silently depending on a future
portfolio-selection decision.

Promotion may additionally record explicit ordered model substitutions through
`WorkflowProductionModelSubstitution`.

Promotion persists two different forms of production information:

```text
WorkflowProductionState
    current production intent
    execution authority

WorkflowProductionRevision
    immutable deployment history
    audit evidence
```

These concepts must not be conflated.

## Production State

`WorkflowProductionState` is the durable description of what a workflow should
execute in production now.

It contains:

- the materialized production workflow specification
- explicit production model substitutions
- explicit production emissions

Production prompt steps must resolve to fixed model selections.

The state may permit ordered substitutes for a prompt step, but those
substitutes are explicitly authorized in production state.

There is no implicit portfolio failover during production execution.

## Production Revisions

`WorkflowProductionRevision` records an immutable historical production
deployment.

Revisions can be persisted through
`WorkflowProductionRevisionRepository` implementations, including:

- `InMemoryWorkflowProductionRevisionRepository`
- `SQLiteWorkflowProductionRevisionRepository`

A revision is audit history.

It is not execution authority.

Production execution does not determine behavior by asking for the newest
revision or by following an active revision pointer.

Current execution behavior comes from `WorkflowProductionState`.

## Production Model Resolution

Production model resolution is deterministic and explicit.

For a prompt-backed production step:

```text
fixed primary model
        │
        ├── executable ──────► use primary
        │
        ▼
ordered explicit substitutes
        │
        ├── executable ──────► use first executable substitute
        │
        ▼
explicit failure
```

Resolution is provided by `resolve_production_model_selection`.

Relevant failures include:

- `ProductionPrimaryModelUnavailableError`
- `ProductionModelSubstitutesUnavailableError`

Production never silently expands its model authority beyond the models
recorded in production state.

## Production Invocation

`ProductionInvocation` records one external call against a workflow identity.

It is created independently of any production revision identity.

The invocation service receives the workflow's active production state and
executes against that state.

```text
ProductionInvocation
        +
WorkflowProductionState
        │
        ▼
generate_production_workflow_candidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

`invoke_production_workflow` coordinates this lifecycle.

The durable invocation result is represented by:

- `ProductionInvocationSuccess`
- `ProductionInvocationFailure`

Failure classification is provided by `ProductionInvocationErrorCode`.

## Invocation and Run Identity

Production invocation and workflow execution remain separately identifiable.

`ProductionInvocationRun` associates one production invocation with the
`WorkflowRun` that provides its empirical execution evidence.

This allows the system to retain both:

```text
external caller identity
        │
ProductionInvocation
        │
ProductionInvocationRun
        │
WorkflowRun
        │
empirical execution evidence
```

without collapsing the two concepts into one record.

## Production Emissions

A production workflow may explicitly declare caller-visible outputs using
`WorkflowProductionEmission`.

Production emissions reference declared workflow step outputs.

`emit_production_result` projects completed workflow execution into the
declared production response.

An invalid declared emission fails explicitly with `ProductionEmissionError`.

Internal workflow execution evidence therefore remains richer than the
caller-visible production result.

## Persistence

The workflow package defines persistence contracts separately from domain
behavior.

Durable repositories include contracts for:

- workflow specifications
- workflow runs
- run evaluations
- feedback
- experiments
- current production state
- immutable production revisions
- production invocations
- invocation/run associations

Both deterministic in-memory implementations and SQLite implementations are
provided for the relevant repository contracts.

Repositories store domain state.

They do not own workflow orchestration, provider access, optimization policy,
or runtime composition.

## Architectural Boundaries

The V1 workflow architecture deliberately maintains the following separations:

```text
WorkflowSpecification
    durable configured intent

WorkflowCandidate
    executable realization

WorkflowRun
    immutable execution evidence

WorkflowEvaluation / WorkflowRunEvaluation
    judgment of evidence

WorkflowExperimentResult
    empirical comparison

WorkflowProductionState
    current durable production intent
    execution authority

WorkflowProductionRevision
    immutable deployment history

ProductionInvocation
    durable external production call
```

These boundaries allow configuration, execution, experimentation,
optimization, deployment, and production operation to evolve independently
without allowing historical evidence or process-local runtime state to become
implicit production authority.