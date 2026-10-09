# Command-Line Interface

`azathoth.cli` is Azathoth's installed operator surface.

It connects durable SQLite configuration, current provider state, executable
runtime composition, empirical workflow operations, and explicit production
operations through one command-line application.

```text
operator
   │
   ▼
azathoth CLI
   │
   ├── durable configuration
   ├── current provider state
   ├── runtime composition
   ├── workflow execution
   ├── empirical optimization
   └── explicit production operations
```

The CLI does not define a second architecture beside the Python domain model.

It composes and exposes the same V1 boundaries through operational commands.

# Application

Installing Azathoth exposes:

```bash
azathoth
```

The package also supports:

```bash
python -m azathoth.cli
```

Basic shell operations include:

```bash
azathoth
azathoth --help
azathoth --version
```

Running the application without a recognized command prints help.

# V1 Command Surface

The V1 command hierarchy is:

```text
azathoth
│
├── --help
├── --version
│
├── workflow
│   ├── import <FILE>
│   ├── list
│   ├── show <WORKFLOW_ID>
│   ├── run <WORKFLOW_ID>
│   ├── optimize <WORKFLOW_ID>
│   │   ├── --expected <JSON>
│   │   ├── --target-latency <SECONDS>
│   │   ├── --target-cost <USD>
│   │   └── --generations <COUNT>
│   ├── promote <WORKFLOW_ID>
│   ├── invoke <WORKFLOW_ID>
│   │   └── --input <JSON>
│   ├── experiments <WORKFLOW_ID>
│   │   └── --limit <COUNT>
│   └── runs <WORKFLOW_ID>
│       └── --limit <COUNT>
│
├── run
│   ├── show <RUN_ID>
│   └── feedback <RUN_ID>
│       ├── --good | --bad          (exactly one)
│       ├── --reason <TEXT>         (required with --bad)
│       └── --corrected-output <JSON>   (only with --bad)
│
├── experiment
│   └── show <EXPERIMENT_ID>
│
├── model
│   ├── list
│   ├── show <MODEL_IDENTIFIER>
│   ├── authorize <MODEL_IDENTIFIER>
│   ├── deauthorize <MODEL_IDENTIFIER>
│   │   └── --force
│   ├── portfolio
│   └── usage <MODEL_IDENTIFIER>
│
├── tool
│   ├── import <FILE>
│   ├── list
│   ├── show <TOOL_ID>
│   │   └── --version <VERSION>
│   ├── versions <TOOL_ID>
│   ├── implementations <TOOL_ID>
│   │   └── --version <VERSION>
│   ├── implementation-show <IMPLEMENTATION_ID>
│   ├── test-cases <TOOL_ID>
│   ├── test-case-show <TEST_CASE_ID>
│   ├── verify <TOOL_ID>
│   │   └── --version <VERSION>
│   └── usage <TOOL_ID>
│
├── goal
│   ├── import <FILE>
│   ├── list
│   └── show <GOAL_ID>
│
└── benchmark
    ├── import <FILE>
    ├── list
    ├── show <BENCHMARK_ID>
    ├── cases <BENCHMARK_ID>
    ├── case-show <BENCHMARK_ID> <CASE_ID>
    ├── run <BENCHMARK_ID>
    │   ├── --workflow <WORKFLOW_ID>
    │   └── --output <OUTPUT>
    └── compare <BENCHMARK_ID>
        ├── --workflow <WORKFLOW_ID>   (repeat for each workflow)
        ├── --output <OUTPUT>
        ├── --target-latency <SECONDS>
        └── --target-cost <USD>
```

This is the actual V1 operator surface.

# Architectural Role

The CLI owns application composition.

Conceptually:

```text
shell command
      │
      ▼
argument parsing
      │
      ▼
CliRuntimeConfiguration
      │
      ▼
load_runtime()
      │
      ▼
AzathothRuntime
      │
      ▼
domain/application service
      │
      ▼
human-readable result
```

The CLI is responsible for:

```text
reading process-local configuration

opening durable repositories

reconstructing runtime state

discovering current provider state when configured

dispatching explicit operator actions

rendering command results

mapping command failure to process exit status
```

It does not replace the underlying domain boundaries.

# Runtime Configuration

`CliRuntimeConfiguration` is immutable process-local CLI configuration.

V1 recognizes:

```text
AZATHOTH_DATABASE

OPENROUTER_API_KEY
```

# AZATHOTH_DATABASE

`AZATHOTH_DATABASE` selects the SQLite database used for durable Azathoth
configuration and operational evidence.

Example:

```bash
export AZATHOTH_DATABASE=/path/to/azathoth.db
```

When the variable is absent, the default is:

```text
azathoth.db
```

relative to the current working directory.

# OPENROUTER_API_KEY

`OPENROUTER_API_KEY` supplies process-local OpenRouter credentials.

Example:

```bash
export OPENROUTER_API_KEY=...
```

The credential is used when CLI runtime composition requires current OpenRouter
model state and executable OpenRouter model implementations.

It is not persisted as workflow configuration.

# Durable Configuration Versus Process Configuration

These are distinct:

```text
SQLite
    durable Azathoth state

environment variables
    process-local CLI configuration
```

For example:

```text
workflow specifications
model portfolio authorization
production state
production revisions
runs
invocations
```

may be durable database artifacts.

The OpenRouter API key remains process-local configuration.

# Runtime Bootstrap

Commands requiring executable runtime state call:

```text
CliRuntimeConfiguration.from_environment()
               │
               ▼
          load_runtime()
               │
               ▼
        AzathothRuntime
```

`load_runtime()` reconstructs and composes:

```text
WorkflowCatalog

WorkflowProductionState collection

current ModelCatalog

ModelPortfolio

LanguageModelRegistry

ToolCatalog

ToolImplementationCatalog
```

The resulting `AzathothRuntime` is a process-local snapshot.

# Workflow Reconstruction

Configured workflows are loaded from:

```text
SQLiteWorkflowRepository
        │
        ▼
WorkflowCatalogLoader
        │
        ▼
WorkflowCatalog
```

The CLI does not maintain a separate workflow configuration representation.

# Production-State Reconstruction

Current production execution authority is loaded from:

```text
SQLiteWorkflowProductionStateRepository
        │
        ▼
WorkflowProductionState(s)
        │
        ▼
AzathothRuntime
```

These states are runtime inputs.

Production revisions are not used as a substitute for current production
state.

# Current Provider Models

When `OPENROUTER_API_KEY` is configured, runtime bootstrap reconstructs current
provider model truth through:

```text
OpenRouterModelDirectory
        │
        ▼
ProviderModelObserver
        │
        ▼
ProviderModelCatalogSynchronizer
        │
        ▼
ModelCatalog
```

Provider observations are persisted separately from the current catalog.

If no OpenRouter API key is configured, the current model catalog is empty.

# Executable Language Models

When OpenRouter credentials are configured, the CLI also builds executable
language-model implementations for the current model catalog.

```text
ModelCatalog
      +
OpenRouterConfiguration
      │
      ▼
OpenRouterModelRegistryLoader
      │
      ▼
LanguageModelRegistry
```

Without an API key, the executable language-model registry is empty.

# Model Portfolio

Organizational model authorization is reconstructed independently:

```text
SQLiteModelPortfolioRepository
        │
        ▼
ModelPortfolioLoader
        │
        ▼
ModelPortfolio
```

This preserves the distinction:

```text
current provider availability
    ≠
organizational authorization
```

# Tool Runtime State

Tool definitions and durable implementation artifacts are reconstructed through:

```text
SQLiteToolRepository
        │
        ▼
ToolCatalogLoader
        │
        ├── ToolCatalog
        └── ToolImplementationCatalog
```

`AzathothRuntime` then composes the corresponding resolution services.

# Shell Help Does Not Require Runtime Bootstrap

Commands such as:

```bash
azathoth --help
azathoth --version
azathoth workflow --help
azathoth run --help
azathoth experiment --help
azathoth model --help
azathoth tool --help
azathoth goal --help
azathoth benchmark --help
```

are parser operations.

They do not require successful provider discovery or workflow execution.

The runtime is reconstructed only when the dispatched command actually needs
application state.

# Workflow Commands

The workflow command family exposes the configured, empirical, and production
workflow lifecycle.

```text
WorkflowSpecification
        │
        ▼
workflow import
        │
        ▼
workflow list / show
        │
        ├──────────────► workflow run ──────► workflow runs / run show
        │
        ├──────────────► workflow optimize
        │
        ▼
workflow promote
        │
        ▼
WorkflowProductionState
        │
        ▼
workflow invoke
```

Each command has a different architectural meaning.

# Import a Workflow

Import a serialized workflow document with:

```bash
azathoth workflow import <FILE>
```

For example:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json
```

The path is:

```text
JSON file
   │
   ▼
workflow document decode / validation
   │
   ▼
WorkflowSpecification
   │
   ▼
SQLiteWorkflowRepository
```

Import persists durable workflow intent.

It does not execute the workflow.

It does not optimize the workflow.

It does not promote the workflow.

# Canonical Workflow Documents

Workflow import accepts the canonical serialized `WorkflowSpecification`
document format.

The checked-in example:

```text
examples/workflows/simple-prompt.json
```

is a complete domain serialization rather than a second simplified CLI schema.

That keeps:

```text
Python domain model
    =
CLI durable document model
```

instead of introducing parallel representations.

# Import Does Not Require Provider Execution

Import operates on serialized durable workflow intent.

It does not need to generate executable workflow candidates.

Therefore a workflow document can be imported without provider credentials when
its validation itself does not require external provider state.

# List Workflows

List durable configured workflows with:

```bash
azathoth workflow list
```

The command operates on configured workflow specifications.

It does not execute them.

# Show a Workflow

Inspect one durable workflow with:

```bash
azathoth workflow show <WORKFLOW_ID>
```

The identifier is a workflow UUID.

The command renders workflow metadata and configured step structure.

It does not need to turn that specification into a `WorkflowCandidate` merely
to inspect it.

# Inspection Versus Execution

This distinction is deliberate:

```text
workflow list
workflow show
      │
      ▼
WorkflowSpecification
```

versus:

```text
workflow run
      │
      ▼
candidate generation
      │
      ▼
WorkflowRun
```

Inspection is durable-state observation.

Execution requires executable runtime composition.

# Run a Configured Workflow

Execute the currently configured workflow with:

```bash
azathoth workflow run <WORKFLOW_ID>
```

This is the **configured workflow execution** command.

The path is:

```text
WorkflowSpecification
        │
        ▼
AzathothRuntime.generate_workflow_candidate()
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
        ├── SQLiteWorkflowRunRepository
        │
        ▼
rendered to the operator
```

The completed run is persisted before it is rendered.

# `workflow run` Is Development/Configured Execution

`workflow run` does not mean:

```text
invoke whatever is deployed in production
```

It means:

```text
generate and execute the configured workflow
```

This distinction is fundamental.

```text
workflow run
    configured workflow path

workflow invoke
    active production path
```

# Run Exit Status

A configured workflow command returns a successful process exit when the
resulting `WorkflowRun` succeeded.

If the run completes unsuccessfully, the CLI returns a failure exit status.

Configuration or candidate-generation failures are emitted to standard error
and also return failure.

# Configured Runs Are Persisted

Every completed configured run is persisted as durable evidence, whether it
succeeded or failed.

```text
workflow run
    succeeded run     persisted
    failed run        persisted

candidate generation fails
    no run exists     nothing persisted
```

The rendered output includes the run ID, so a run can be revisited later with
`run show`.

Configured, experiment, and production runs share one durable run history.
They are distinguished by association, not by separate storage:

```text
WorkflowRun associated with a ProductionInvocation
    production run

WorkflowRun observed by a WorkflowExperimentRecord
    experiment run

every other persisted WorkflowRun
    configured run
```

When a run is both, production takes precedence.

Persisted configured runs also feed the history half of `model usage` and
`tool usage`.

# List Workflow Runs

List persisted runs of one workflow with:

```bash
azathoth workflow runs <WORKFLOW_ID>
```

Limit the listing to the most recent runs with:

```bash
azathoth workflow runs <WORKFLOW_ID> --limit <COUNT>
```

`--limit` must be a positive integer.

Runs are listed newest first, one line per run:

```text
<RUN_ID>  2026-10-02T12:10:00+00:00  succeeded  1.500s  configured  good
<RUN_ID>  2026-10-02T12:07:00+00:00  succeeded  0.900s  experiment  -
<RUN_ID>  2026-10-02T12:05:00+00:00  failed     0.250s  production  -
```

Each line contains the run ID, start time, status, duration, source, and the
run's latest feedback disposition. Runs that have not been judged show `-`.

"Latest" means the most recent feedback timestamp, not the most recently saved
record. When timestamps tie, the later-saved record wins.

The limit is applied after sorting, so `--limit 5` means the five most recent
runs.

A configured workflow with no runs prints nothing and exits successfully.

Runs of a workflow since removed from configuration remain listable.

An identifier that is neither configured nor present in run history fails
with:

```text
Workflow <WORKFLOW_ID> is not configured.
```

so a mistyped identifier is not mistaken for a workflow that never ran.

# Show a Run

Inspect one persisted run with:

```bash
azathoth run show <RUN_ID>
```

The run is rendered exactly as `workflow run` rendered it: identity, status,
statistics, and per-step evidence, followed by every feedback record for that
run, oldest first.

Each executed step also lists the resources its strategy bound:

```text
Resource: model openrouter/some-model
Resource: tool <IMPLEMENTATION_ID> (runtime=python, tool_id=<TOOL_ID>, tool_version=1.0.0)
```

Attributes are sorted by name. Structured attribute values render as compact
JSON.

This is the reverse of usage discovery:

```text
model usage / tool usage
    which runs used this resource?

run show
    which resources did this run use?
```

A run with no feedback ends with:

```text
Feedback: none
```

An unknown run fails with:

```text
Run <RUN_ID> was not found.
```

`workflow runs` and `run show` read durable state only. They do not require
provider credentials or runtime bootstrap.

# Judge a Run

Record a judgment about one persisted run with:

```bash
azathoth run feedback <RUN_ID> --good [--reason <TEXT>]
```

or:

```bash
azathoth run feedback <RUN_ID> --bad --reason <TEXT> \
    [--corrected-output '<JSON>']
```

Exactly one of `--good` or `--bad` is required.

Each judgment is an immutable `WorkflowRunFeedback` record:

```text
WorkflowRunFeedback
├── id
├── run_id
├── disposition         good | bad
├── reason              optional for good, required for bad
├── corrected_output    optional JSON, bad only
└── created_at
```

A run can collect any number of judgments. Later judgments do not replace
earlier ones; `workflow runs` shows the latest disposition and `run show` shows
the full history.

On success the command prints:

```text
Recorded bad feedback <FEEDBACK_ID> for run <RUN_ID>.
```

# Feedback Rules

Feedback is accepted only when it is coherent:

```text
unknown run
    Run <RUN_ID> was not found.

--good with --corrected-output
    A corrected output can only accompany bad feedback.

--bad without a reason
    Bad workflow run feedback requires a reason.
```

A run that needed correcting was not good, so a corrected output is accepted
only with `--bad`.

Reasons are trimmed. A blank reason is treated as absent, so a whitespace-only
reason does not satisfy `--bad`.

Every rejection exits with failure and saves nothing.

Malformed `--corrected-output` JSON and missing or conflicting dispositions are
rejected by the parser before any durable state is read.

# Feedback Is Evidence

Bad runs with corrected outputs record what a workflow should have produced
for a real input:

```text
WorkflowRun
    actual input and output

WorkflowRunFeedback
    judgment, reason, and corrected output
```

That pairing is durable evidence about workflow correctness, recorded by the
operator rather than inferred.

Recording feedback never changes the run it judges, the workflow
specification, or production state.

# Empirically Optimize a Workflow

Run empirical workflow optimization with:

```bash
azathoth workflow optimize <WORKFLOW_ID> \
    --expected '<JSON>' \
    --target-latency <SECONDS> \
    --target-cost <USD>
```

Optional generation count:

```bash
--generations <COUNT>
```

The default is:

```text
1
```

# Optimization Arguments

`--expected` is required and must be valid JSON.

Examples:

```bash
--expected '"success"'
```

or:

```bash
--expected '{"classification":"positive"}'
```

`--target-latency` is required and is interpreted as seconds.

`--target-cost` is required and is interpreted as USD.

`--generations` controls the maximum number of empirical optimization
generations.

# CLI Expected Outcome

The CLI converts the supplied `--expected` JSON value into:

```text
ExpectedOutcome
├── description
├── value = operator-supplied JSON
└── comparison = exact
```

The V1 CLI therefore uses exact expected-output evaluation for this command.

# CLI Scoring Targets

The CLI constructs a workflow scoring policy from:

```text
target latency

target cost
```

These are scoring inputs used during the empirical workflow optimization
session.

They are not silently persisted as production policy by the CLI command.

# Optimization Lifecycle

Conceptually:

```text
configured WorkflowSpecification
        │
        ▼
runtime candidate generation
        │
        ▼
execute
        │
        ▼
evaluate against --expected
        │
        ▼
score using latency / cost targets
        │
        ▼
rank empirical evidence
        │
        ▼
optimizer proposes next generation
        │
        ▼
WorkflowOptimizationSession
```

The completed session is rendered to the operator.

# Optimization Evidence Is Persisted

Every generation of `workflow optimize` leaves durable evidence:

```text
each candidate execution
    WorkflowRun                 persisted, succeeded or failed

each successful execution
    WorkflowRunEvaluation       persisted

each generation
    WorkflowExperimentRecord    persisted
```

An experiment record holds one observation per successfully executed
candidate, each referencing its run, its evaluation, its candidate signature,
and its scorecard, plus the ranking of those runs.

The record shares the identity of the in-memory experiment result, so the
rendered session names it directly:

```text
Generation 1
Experiment ID: <EXPERIMENT_ID>
Evaluated Candidates: 2
```

From there the evidence chain is navigable from bash:

```text
workflow optimize
        │
        ▼
Experiment ID ──► experiment show
                        │
                        ▼
                 Run ID ──► run show / run feedback
```

A generation in which every candidate fails raises before ranking. Its failed
runs remain persisted; no experiment record is written.

Failed candidates appear as runs but not as experiment observations, because
records hold only scored, ranked observations. As a consequence a failed
optimization candidate is currently listed with the `configured` source.

# List Workflow Experiments

List persisted experiments containing one workflow with:

```bash
azathoth workflow experiments <WORKFLOW_ID>
```

Limit the listing to the most recent experiments with:

```bash
azathoth workflow experiments <WORKFLOW_ID> --limit <COUNT>
```

`--limit` must be a positive integer.

Experiments are listed newest first, one line per experiment:

```text
<EXPERIMENT_ID>  2026-10-09T16:05:00+00:00  2 candidates  winner <RUN_ID>  overall 0.900000
```

Each line contains the experiment ID, recorded time, candidate count, winning
run, and winning overall score.

A configured workflow with no experiments prints nothing and exits
successfully.

Experiments of a workflow since removed from configuration remain listable.

An identifier that is neither configured nor present in experiment history
fails with:

```text
Workflow <WORKFLOW_ID> is not configured.
```

# Show an Experiment

Inspect one persisted experiment with:

```bash
azathoth experiment show <EXPERIMENT_ID>
```

The experiment is rendered with every observation in rank order, not
candidate order:

```text
Experiment ID: <EXPERIMENT_ID>
Recorded: 2026-10-09T16:05:00+00:00
Candidates: 2
Winner Run ID: <RUN_ID>

Rank 1
Workflow: summarize
Workflow ID: <WORKFLOW_ID>
Run ID: <RUN_ID>
Evaluation ID: <EVALUATION_ID>
Strategy IDs: <STRATEGY_ID>
Quality: 1.000000
Reliability: 1.000000
Latency: 0.950000
Cost: 0.800000
Overall: 0.900000
```

A scorecard rationale is rendered when one was recorded.

An unknown experiment fails with:

```text
Experiment <EXPERIMENT_ID> was not found.
```

`workflow experiments` and `experiment show` read durable state only. They do
not require provider credentials or runtime bootstrap.

# Optimization Does Not Promote

This is one of the most important V1 CLI boundaries.

```text
azathoth workflow optimize ...
```

does **not** update:

```text
WorkflowProductionState
```

and does not automatically deploy the optimizer's empirical winner.

Optimization produces durable evidence and candidate-search results.

Production promotion is a separate explicit operator action.

```text
optimize
    ≠
promote
```

# Promote a Workflow

Explicitly promote a configured workflow with:

```bash
azathoth workflow promote <WORKFLOW_ID>
```

This command generates the configured workflow candidate and passes it through
the production-promotion domain service.

Conceptually:

```text
configured WorkflowSpecification
        │
        ▼
runtime candidate generation
        │
        ▼
WorkflowCandidate
        │
        ▼
explicit promotion
        │
        ├── WorkflowProductionState
        └── WorkflowProductionRevision
```

# Promotion Is Explicit

Nothing about:

```text
workflow run

workflow optimize
```

implicitly promotes a workflow.

The operator must invoke:

```bash
azathoth workflow promote <WORKFLOW_ID>
```

to change active production intent.

# Production State Is Execution Authority

Promotion persists:

```text
WorkflowProductionState
```

as current production execution authority.

It also persists:

```text
WorkflowProductionRevision
```

as immutable audit history.

The distinction remains:

```text
production state
    current execution authority

production revision
    historical audit evidence
```

The CLI does not turn "latest revision" into production authority.

# Promotion Materializes Executable Model Intent

When a configured prompt step uses portfolio-based model selection, promotion
materializes the generated candidate's chosen model into fixed production model
selection.

Conceptually:

```text
PortfolioModelSelection
        │
        ▼
candidate generation
        │
        ▼
chosen executable model
        │
        ▼
promotion
        │
        ▼
FixedModelSelection
```

Production therefore records explicit model intent rather than depending on a
new portfolio choice on every invocation.

# Promotion Rendering

Successful promotion rendering includes production-oriented details such as:

```text
workflow name

workflow ID

revision ID

promotion status

creation time

prompt step IDs

fixed primary model

ordered substitute models when configured
```

The revision ID is displayed as audit identity.

It is not used by `workflow invoke` as execution authority.

# Invoke Active Production

Invoke one active production workflow with:

```bash
azathoth workflow invoke <WORKFLOW_ID> \
    --input '<JSON>'
```

`--input` is required and must be valid JSON.

For example:

```bash
azathoth workflow invoke \
    11111111-1111-1111-1111-111111111111 \
    --input '{"request":"execute production"}'
```

# Production Invocation Lifecycle

The command follows:

```text
workflow ID
    +
JSON payload
      │
      ▼
load_runtime()
      │
      ▼
runtime.production_state(workflow_id)
      │
      ▼
invoke_production_workflow()
      │
      ├── durable ProductionInvocation
      │
      ├── WorkflowRun
      │
      └── durable invocation/run association
      │
      ▼
ProductionInvocationResult
```

The production state embedded in the reconstructed runtime determines intended
production behavior.

# `workflow invoke` Is Not `workflow run`

These commands deliberately expose different execution authorities.

```text
workflow run
      │
      ▼
configured WorkflowSpecification
      │
      ▼
generate candidate now
```

versus:

```text
workflow invoke
      │
      ▼
active WorkflowProductionState
      │
      ▼
execute production intent
```

This is not merely naming.

It is an architectural boundary.

# Undeployed Workflow Invocation

If no active production state exists for the requested workflow, invocation
fails explicitly.

The CLI does not silently fall back to:

```text
configured WorkflowSpecification
```

and does not promote the workflow automatically.

```text
no production state
       │
       ▼
production invocation failure
```

# Durable Production Invocation Evidence

Production invocation uses SQLite repositories for:

```text
ProductionInvocation

WorkflowRun

ProductionInvocationRun association
```

This preserves a durable relationship between:

```text
external production call

and

empirical workflow execution
```

# Invocation Result Rendering

On success, the CLI renders:

```text
Invocation ID

Status: succeeded

Result
```

On failure, it renders:

```text
Invocation ID

Status: failed

error code

message

optional metadata
```

Production failures are written to standard error and return a failure process
exit status.

# Promotion Followed by Invocation

The V1 CLI supports the explicit production lifecycle:

```bash
azathoth workflow promote <WORKFLOW_ID>

azathoth workflow invoke <WORKFLOW_ID> \
    --input '<JSON>'
```

Conceptually:

```text
configured workflow
      │
      ▼
promote
      │
      ▼
active production state
      │
      ▼
invoke
      │
      ▼
durable production execution evidence
```

This is the operator boundary for moving configured behavior into production.

# No Dedicated Rollback Command in V1

V1 does not expose:

```text
azathoth workflow rollback
```

Production changes remain explicit promotions.

A dedicated rollback convenience operation is not part of the frozen V1
operator surface.

The important architecture remains:

```text
current WorkflowProductionState
    determines what production executes
```

not:

```text
implicitly execute the newest historical revision
```

# Model Commands

The model command family exposes current provider availability and
organizational authorization.

```text
azathoth model
├── list
├── show
├── authorize
├── deauthorize
├── portfolio
└── usage
```

The CLI does not use one command to conflate these concepts.

# List Current Models

List currently available provider models with:

```bash
azathoth model list
```

This command reflects the current model catalog reconstructed during CLI
runtime bootstrap.

Conceptually:

```text
current provider discovery
        │
        ▼
ModelCatalog
        │
        ▼
model list
```

# Show a Current Model

Inspect one currently available provider model with:

```bash
azathoth model show <MODEL_IDENTIFIER>
```

The identifier is provider-qualified:

```text
provider/model
```

For example:

```text
openrouter/some-model
```

The command inspects current model metadata.

# Authorize a Model

Authorize one currently available provider model for organizational selection
with:

```bash
azathoth model authorize <MODEL_IDENTIFIER>
```

Authorization changes the durable `ModelPortfolio`.

The distinction is:

```text
model exists in current provider catalog
    availability

model exists in ModelPortfolio
    organizational authorization
```

Authorization does not create provider availability.

# Authorization Requires Current Availability

The authorize operation acts on a currently available provider model.

The CLI does not use authorization as a mechanism for inventing model metadata
that the current provider catalog does not contain.

This maintains:

```text
current availability
    before
organizational authorization
```

# Deauthorize a Model

Remove organizational authorization with:

```bash
azathoth model deauthorize <MODEL_IDENTIFIER>
```

This changes portfolio membership.

It does not delete the model from provider discovery.

```text
provider model remains current
        │
        ▼
portfolio authorization removed
```

Availability and authorization remain separate.

# Deauthorization Is Guarded by Production

Deauthorization is refused while any active `WorkflowProductionState` holds
the model as a step's primary model or as an approved substitute.

The command exits with failure, leaves the portfolio unchanged, and names each
dependent workflow and step on standard error:

```text
Model 'openrouter/some-model' is used by active production and was not deauthorized.
  summarize (<WORKFLOW_ID>): primary step <STEP_ID>
Use --force to deauthorize anyway.
```

An operator who accepts that consequence can proceed explicitly:

```bash
azathoth model deauthorize <MODEL_IDENTIFIER> --force
```

Forced deauthorization removes portfolio membership and still reports the
dependent production workflows on standard error as a warning.

Only active production blocks deauthorization.

Configured workflows that pin the model, and historical runs that executed it,
do not. Use `model usage` to inspect those before deauthorizing.

# Trace Model Usage

Show everywhere one exact model is depended upon with:

```bash
azathoth model usage <MODEL_IDENTIFIER>
```

The report is grouped by workflow and combines three independent sources:

```text
configured
    a durable WorkflowSpecification pins the model with fixed selection

production
    an active WorkflowProductionState holds the model as primary or substitute

history
    a persisted WorkflowRun recorded a successful execution bound to the model
```

Portfolio-based model selection is not counted as configured usage, because
the model is not pinned; it is only eligible.

Workflows deleted from configuration still appear when production state or run
history references them. That is the case where the question "what depends on
this model?" matters most.

`model usage` reads durable state only. It does not require provider
credentials or current provider availability, so a model a provider has stopped
offering can still be traced.

An unused model reports zero workflows and exits successfully.

# List the Portfolio

Inspect authorized models with:

```bash
azathoth model portfolio
```

This exposes the durable organizational selection universe represented by
`ModelPortfolio`.

It is distinct from:

```bash
azathoth model list
```

which represents current provider availability.

# `model list` Versus `model portfolio`

The difference is:

```text
model list
    what the provider currently exposes

model portfolio
    what the organization has authorized
```

That distinction directly supports portfolio-based workflow candidate
generation.

# Model Commands Do Not Define Production Model Authority

Portfolio authorization affects eligible model selection in portfolio-selected
configured workflows.

Production prompt steps use fixed production model selection.

Therefore:

```text
model authorize
    ≠
change active production primary automatically

model deauthorize
    ≠
rewrite active WorkflowProductionState automatically
```

Production authority remains explicit and durable.

Because deauthorization never rewrites production state, it refuses by default
when production depends on the model rather than leaving production pinned to
a model the organization no longer authorizes.

# Model Availability Is Dynamic

Current provider state may change between CLI invocations.

Because the runtime is reconstructed for a command, a later command may observe
different current provider truth.

```text
command A
    runtime snapshot A

provider changes

command B
    runtime snapshot B
```

Durable portfolio authorization and durable workflow intent remain separate
from that changing provider state.

# Tool Commands

The tool command family exposes durable tool definitions, their executable
implementations, and their verification cases.

```text
azathoth tool
├── import
├── list
├── show
├── versions
├── implementations
├── implementation-show
├── test-cases
├── test-case-show
├── verify
└── usage
```

A tool identity is a UUID shared by every definition version of that tool.

Commands that act on one exact definition version take:

```bash
--version <VERSION>
```

# Trace Tool Usage

Show everywhere one tool identity is depended upon with:

```bash
azathoth tool usage <TOOL_ID>
```

Workflows require tools by capability name, while execution history records
the durable tool identity:

```text
ToolRequirement.name
    configured and production usage

tool identity (UUID)
    historical execution provenance
```

The report resolves capability names from every definition version sharing the
tool identity, so a tool renamed between versions is still traced under each
name. Requirement version constraints are not used to narrow configured or
production matches.

Historical entries include the implementation, tool version, and runtime that
actually executed.

A tool identity is known when any definition version exists or when run
history recorded its execution. An unknown identity fails with:

```text
Tool <TOOL_ID> is not configured.
```

so a mistyped identifier is not mistaken for an unused tool.

# Goal Commands

The goal command family manages durable reusable goals.

```bash
azathoth goal import <FILE>
azathoth goal list
azathoth goal show <GOAL_ID>
```

# Benchmark Commands

The benchmark command family manages durable benchmark datasets and evaluates
configured workflows against them.

```bash
azathoth benchmark import <FILE>
azathoth benchmark list
azathoth benchmark show <BENCHMARK_ID>
azathoth benchmark cases <BENCHMARK_ID>
azathoth benchmark case-show <BENCHMARK_ID> <CASE_ID>
```

Execute one configured workflow against a dataset with:

```bash
azathoth benchmark run <BENCHMARK_ID> \
    --workflow <WORKFLOW_ID> \
    --output <OUTPUT>
```

Compare several configured workflows against one dataset with:

```bash
azathoth benchmark compare <BENCHMARK_ID> \
    --workflow <WORKFLOW_ID> \
    --workflow <WORKFLOW_ID> \
    --output <OUTPUT> \
    --target-latency <SECONDS> \
    --target-cost <USD>
```

`--output` names the workflow output value evaluated against each case.

Benchmarking executes configured workflows.

Like optimization, it produces evidence and does not promote.

# CLI JSON Arguments

The CLI parser accepts JSON-compatible command-line values for:

```text
workflow invoke --input

workflow optimize --expected
```

Values are parsed using JSON rather than treated as raw strings.

Therefore:

```bash
--expected '"success"'
```

represents the JSON string:

```text
success
```

while:

```bash
--expected '{"status":"success"}'
```

represents a structured object.

Invalid JSON is rejected at the command boundary.

# CLI Exit Semantics

V1 commands use process exit codes to distinguish success and failure.

Conceptually:

```text
0
    command succeeded

non-zero
    command or domain operation failed
```

Domain errors intended for operators are printed to standard error.

Successful human-readable results are printed to standard output.

# CLI Rendering

Rendering is deliberately separate from domain operations.

The CLI contains human-readable renderers for:

```text
WorkflowRun

WorkflowRun summaries

WorkflowRunFeedback

WorkflowExperimentRecord / WorkflowExperimentRecord summaries

WorkflowOptimizationSession

WorkflowProductionRevision

ProductionInvocationResult

WorkflowBenchmarkResult / WorkflowBenchmarkRanking

WorkflowModelUsageReport

WorkflowToolUsageReport
```

The renderers consume completed domain artifacts.

They do not perform the underlying operation.

```text
domain result
      │
      ▼
renderer
      │
      ▼
operator-facing text
```

# CLI Application Services

The CLI contains thin application services around lower-level Azathoth domains.

Examples include:

```text
execute_configured_workflow

optimize_configured_workflow

promote_configured_workflow

invoke_active_production_workflow
```

These functions compose runtime state and domain services for application use.

They do not create parallel domain models.

# Configured Execution Application Service

Configured execution composes:

```text
RuntimeEnvironment

workflow ID

StrategyExecutor / WorkflowRunner path
```

into a `WorkflowRun`.

Candidate generation remains delegated to the runtime/workflow architecture.

# Optimization Application Service

Configured optimization composes:

```text
runtime

workflow identity

expected outcome

workflow scoring policy

generation limit

evidence recorder
```

into a `WorkflowOptimizationSession`.

The installed CLI always supplies a SQLite-backed
`WorkflowExperimentEvidenceRecorder`, so every generation's runs,
evaluations, and experiment record are persisted. Without a recorder, the
application service behaves exactly as before and keeps no evidence.

The CLI command supplies operator parameters.

The optimization package retains optimization semantics.

# Promotion Application Service

Promotion composes:

```text
runtime

workflow ID

production-state repository

production-revision repository
```

then:

```text
runtime.generate_workflow_candidate()
        │
        ▼
promote_workflow_candidate()
```

The service does not infer an optimization winner.

Promotion remains explicit.

# Production Invocation Application Service

Production invocation composes:

```text
runtime active production state

current model catalog

language-model registry

tool resolvers

invocation repository

workflow-run repository

invocation/run repository
```

into the existing production invocation domain service.

It does not determine production state from revision history.

# CLI and Persistence

The V1 installed application primarily uses SQLite persistence.

The CLI accesses durable repositories for concepts including:

```text
configured workflows

model portfolio

provider model observations

tool definitions and implementations

reusable goals

benchmark datasets

production states

production revisions

workflow runs

workflow run evaluations

workflow experiments

workflow run feedback

production invocations

invocation/run associations
```

Each domain retains its own persistence contract.

The CLI merely chooses concrete SQLite implementations for installed
application operation.

# CLI Does Not Own Domain Persistence Semantics

Using SQLite from the CLI does not move repository semantics into the command
parser.

```text
argparse
    command parsing

CLI application service
    composition

repository
    persistence

domain service
    behavior
```

Those layers remain distinct.

# CLI and Runtime Snapshots

Every command that calls `load_runtime()` receives one reconstructed runtime
snapshot.

If durable state changes later:

```text
existing runtime
    does not mutate itself

next CLI command
    reconstructs new state
```

This matches the runtime architecture.

# CLI and Provider Independence

The CLI currently contains concrete OpenRouter bootstrap support.

The durable Azathoth domains remain provider-neutral.

The CLI is where application-specific provider composition belongs.

```text
provider-neutral domains
        │
        ▼
CLI bootstrap
        │
        ▼
concrete OpenRouter adapter
```

This prevents OpenRouter-specific environment and network concerns from
entering durable workflow definitions.

# CLI and Production Authority

The CLI preserves the most important production boundary in V1:

```text
WorkflowProductionState
    execution authority

WorkflowProductionRevision
    audit history
```

`workflow promote` changes the current state explicitly.

`workflow invoke` executes current state.

No CLI command infers production intent from:

```text
latest revision

latest experiment

latest optimizer winner

latest configured workflow mutation
```

# Complete V1 Operator Lifecycle

The complete operator-facing workflow path is:

```text
                       CONFIGURATION

                    workflow JSON
                         │
                         ▼
                 workflow import
                         │
                         ▼
                WorkflowSpecification
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        workflow list          workflow show


                  CONFIGURED EXECUTION

                WorkflowSpecification
                         │
                         ▼
                    workflow run
                         │
                         ▼
                    WorkflowRun
                         │
                         ▼
             workflow runs / run show


                 EMPIRICAL OPTIMIZATION

                WorkflowSpecification
                         │
                         ▼
                  workflow optimize
                         │
                         ▼
            WorkflowOptimizationSession
                         │
                         ▼
      runs / evaluations / experiment records
                         │
                         ▼
        workflow experiments / experiment show


                   EXPLICIT PROMOTION

                WorkflowSpecification
                         │
                         ▼
                 workflow promote
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
 WorkflowProductionState   WorkflowProductionRevision
   execution authority          audit history
              │
              ▼


                 PRODUCTION EXECUTION

                workflow invoke
                         │
                         ▼
              ProductionInvocation
                         │
                         ▼
                    WorkflowRun
                         │
                         ▼
           ProductionInvocationResult
```

The model operator path remains orthogonal:

```text
current provider state
        │
        ▼
   model list/show
        │
        ▼
model authorize/deauthorize
        │
        ▼
    ModelPortfolio
        │
        ▼
configured candidate generation
```

# V1 CLI Principles

The V1 operator architecture can be summarized as:

```text
inspection
    ≠
execution

run history
    ≠
run execution

run feedback
    ≠
run mutation

experiment evidence
    ≠
experiment outcome

configured execution
    ≠
production invocation

optimization
    ≠
promotion

promotion
    ≠
invocation

production state
    ≠
production revision

provider availability
    ≠
organizational authorization

model portfolio
    ≠
production model authority

usage discovery
    ≠
mutation

durable configuration
    ≠
process-local credentials

CLI composition
    ≠
domain semantics
```

The central operator rule is:

```text
Configure explicitly.

Execute empirically.

Optimize without hidden deployment.

Promote deliberately.

Invoke exactly what production state says to invoke.
```

That makes the CLI a faithful operational surface over Azathoth's V1
architecture rather than a second source of architectural truth.
