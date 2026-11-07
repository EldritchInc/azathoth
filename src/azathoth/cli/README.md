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
├── init
│
├── workflow
│   ├── import <FILE>
│   ├── list
│   ├── show <WORKFLOW_ID>
│   │   └── --revision <NUMBER>
│   ├── history <WORKFLOW_ID>
│   │   └── --limit <COUNT>
│   ├── export <WORKFLOW_ID>
│   │   └── --revision <NUMBER>
│   ├── run <WORKFLOW_ID>
│   │   ├── --input <JSON> | --input-file <FILE>
│   │   └── --media-type <TYPE>     (only with --input-file)
│   ├── optimize <WORKFLOW_ID>
│   │   ├── --benchmark <BENCHMARK_ID>
│   │   ├── --target-latency <SECONDS>
│   │   ├── --target-cost <USD>
│   │   └── --generations <COUNT>
│   ├── promote <WORKFLOW_ID>
│   │   └── --experiment <EXPERIMENT_ID>
│   ├── invoke <WORKFLOW_ID>
│   │   ├── --input <JSON> | --input-file <FILE>   (exactly one)
│   │   ├── --media-type <TYPE>     (only with --input-file)
│   │   └── --idempotency-key <KEY>
│   ├── production <WORKFLOW_ID>
│   ├── revisions <WORKFLOW_ID>
│   │   └── --limit <COUNT>
│   ├── invocations <WORKFLOW_ID>
│   │   └── --limit <COUNT>
│   ├── experiments <WORKFLOW_ID>
│   │   └── --limit <COUNT>
│   └── runs <WORKFLOW_ID>
│       └── --limit <COUNT>
│
├── run
│   ├── show <RUN_ID>
│   ├── annotations <RUN_ID>
│   ├── children <RUN_ID>
│   ├── resume <RUN_ID>
│   │   └── --output <FORMAT>
│   └── feedback <RUN_ID>
│       ├── --good | --bad          (exactly one)
│       ├── --reason <TEXT>         (required with --bad)
│       └── --corrected-output <JSON>   (only with --bad)
│
├── experiment
│   └── show <EXPERIMENT_ID>
│
├── invocation
│   ├── show <INVOCATION_ID>
│   │   └── --links
│   ├── annotations <INVOCATION_ID>
│   └── resume <INVOCATION_ID>
│       └── --output <FORMAT>
│
├── job
│   └── run <FILE | ->
│
├── worker
│   ├── run
│   │   ├── --queue-url <URL>
│   │   ├── --result-queue-url <URL>
│   │   ├── --wait-seconds <SECONDS>
│   │   ├── --visibility-timeout-seconds <SECONDS>
│   │   ├── --extend-every-seconds <SECONDS>
│   │   └── --heartbeat-file <PATH>
│   └── health
│       ├── --heartbeat-file <PATH>
│       └── --max-age-seconds <SECONDS>
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
├── judge
│   ├── add <MODEL_IDENTIFIER>
│   ├── list
│   └── remove <MODEL_IDENTIFIER>
│
├── tool
│   ├── import <FILE>
│   ├── install-standard
│   ├── list
│   ├── show <TOOL_ID>
│   │   └── --version <VERSION>
│   ├── history <TOOL_ID>
│   │   ├── --version <VERSION>
│   │   └── --limit <COUNT>
│   ├── export <TOOL_ID>
│   │   ├── --version <VERSION>
│   │   └── --revision <NUMBER>
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
    │   └── --revision <NUMBER>
    ├── history <BENCHMARK_ID>
    │   └── --limit <COUNT>
    ├── export <BENCHMARK_ID>
    │   └── --revision <NUMBER>
    ├── cases <BENCHMARK_ID>
    ├── case-show <BENCHMARK_ID> <CASE_ID>
    ├── add-case <BENCHMARK_ID>
    │   ├── --from-run <RUN_ID>
    │   ├── --input-file <FILE>   (instead of --from-run)
    │   ├── --media-type <TYPE>
    │   ├── --comparison exact|normalized|semantic|schema
    │   ├── --expected <JSON>
    │   ├── --require-citation <SOURCE:SEGMENT>   (repeat for each segment)
    │   ├── --on-unverified fail|ignore
    │   └── --description <TEXT>
    ├── run <BENCHMARK_ID>
    │   └── --workflow <WORKFLOW_ID>
    ├── compare <BENCHMARK_ID>
    │   ├── --workflow <WORKFLOW_ID>   (repeat for each workflow)
    │   ├── --target-latency <SECONDS>
    │   └── --target-cost <USD>
    ├── executions <BENCHMARK_ID>
    │   └── --limit <COUNT>
    └── execution-show <EXECUTION_ID>
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

Azathoth 1.1 adds `AZATHOTH_OTEL`, which turns tracing on (see
[Tracing](#tracing)), and `AZATHOTH_BEDROCK` and `AZATHOTH_BEDROCK_PRICING`,
which run models on Amazon Bedrock (see [AZATHOTH_BEDROCK](#azathoth_bedrock)),
and `AZATHOTH_CONTENT_STORE`, which keeps resolved input content in Amazon S3
(see [AZATHOTH_CONTENT_STORE](#azathoth_content_store)).

# AZATHOTH_DATABASE

`AZATHOTH_DATABASE` selects the database used for durable Azathoth
configuration and operational evidence: an SQLite file, or, in Azathoth 1.1,
a PostgreSQL database (ADR 0102).

Example:

```bash
export AZATHOTH_DATABASE=/path/to/azathoth.db
```

When the variable is absent, the default is:

```text
azathoth.db
```

relative to the current working directory.

A value that starts with `postgresql://` or `postgres://` names a PostgreSQL
database, and needs the `postgres` extra:

```bash
export AZATHOTH_DATABASE=postgresql://azathoth:<PASSWORD>@db.example.com:5432/azathoth
```

`CliRuntimeConfiguration.database` is then a `PostgresLocation` rather than
a `Path`, and every command opens its repositories through
`open_repositories` (see
[`azathoth.persistence`](../persistence/README.md#opening-the-repositories)).
Commands never show the URL's password.

Every command over a PostgreSQL database that has not been initialized, or
whose schema is not this Azathoth's, prints one line to stderr, writes
nothing, and exits with status 1:

```text
Database postgresql://azathoth@db.example.com:5432/azathoth is not initialized; run azathoth init.
```

Without the `postgres` extra, it prints instead:

```text
AZATHOTH_DATABASE names a PostgreSQL database, but psycopg is not installed; install azathoth-ai[postgres].
```

# Initialize a Database

Start a database with:

```bash
azathoth init
```

```text
Database: /path/to/azathoth.db (created)
Installed tool run_workflow@1.0.0 revision 1.
Installed tool loop_workflow@1.1.0 revision 1.
Installed tool map_workflow@1.0.0 revision 1.
Installed tool json_select@1.0.0 revision 1.
Installed tool json_object@1.0.0 revision 1.
Installed tool json_merge@1.0.0 revision 1.
Installed tool validate_json@1.0.0 revision 1.
Installed tool chunk_text@1.0.0 revision 1.
Installed tool join_text@1.0.0 revision 1.
Installed tool render_template@1.0.0 revision 1.
Installed tool split_s3_object@1.0.0 revision 1.
Installed tool read_s3_object@1.0.0 revision 1.
Installed tool segment_pdf@1.0.0 revision 1.
```

`init` opens the database that `AZATHOTH_DATABASE` names, or `azathoth.db`
in the working directory, creating it and any missing parent directories.
It shows the database as an absolute path, marked `created` or `existing`.
It then installs the standard tool library exactly as `tool install-standard`
does, and exits with that command's status.

Running it again is safe:

```text
Database: /path/to/azathoth.db (existing)
Tool run_workflow@1.0.0 is already installed (revision 1).
Tool loop_workflow@1.1.0 is already installed (revision 1).
Tool map_workflow@1.0.0 is already installed (revision 1).
Tool json_select@1.0.0 is already installed (revision 1).
Tool json_object@1.0.0 is already installed (revision 1).
Tool json_merge@1.0.0 is already installed (revision 1).
Tool validate_json@1.0.0 is already installed (revision 1).
Tool chunk_text@1.0.0 is already installed (revision 1).
Tool join_text@1.0.0 is already installed (revision 1).
Tool render_template@1.0.0 is already installed (revision 1).
Tool split_s3_object@1.0.0 is already installed (revision 1).
Tool read_s3_object@1.0.0 is already installed (revision 1).
Tool segment_pdf@1.0.0 is already installed (revision 1).
```

A database that cannot be opened, for example because the path is a
directory, is reported and nothing is installed:

```text
Unable to open database <PATH>: <ERROR>
```

For a PostgreSQL database, `init` creates the schema, or finds it there,
before it installs the tools, and names the database without its password:

```text
Database: postgresql://azathoth@db.example.com:5432/azathoth (created)
Installed tool run_workflow@1.0.0 revision 1.
Installed tool loop_workflow@1.1.0 revision 1.
Installed tool map_workflow@1.0.0 revision 1.
Installed tool json_select@1.0.0 revision 1.
Installed tool json_object@1.0.0 revision 1.
Installed tool json_merge@1.0.0 revision 1.
Installed tool validate_json@1.0.0 revision 1.
Installed tool chunk_text@1.0.0 revision 1.
Installed tool join_text@1.0.0 revision 1.
Installed tool render_template@1.0.0 revision 1.
Installed tool split_s3_object@1.0.0 revision 1.
Installed tool read_s3_object@1.0.0 revision 1.
Installed tool segment_pdf@1.0.0 revision 1.
```

It is the only command that creates a PostgreSQL schema. Several processes
may run it at once: they wait for one another, and all but the first report
the database as `existing`.

It is also the only command that upgrades one. After Azathoth is upgraded to
a newer schema version, every other command refuses the database until
`init` runs once:

```text
Database postgresql://azathoth@db.example.com:5432/azathoth has schema version 1, but this Azathoth uses version 2; run azathoth init.
```

`init` then adds the tables the database lacks, keeps everything it holds,
and marks it upgraded:

```text
Database: postgresql://azathoth@db.example.com:5432/azathoth (upgraded to schema version 2)
```

`init` stops at the database and its tools. It needs no provider key.
Authorizing models needs provider credentials and the models they make
available, so `model authorize` stays a separate step.

# OPENROUTER_API_KEY

`OPENROUTER_API_KEY` supplies process-local OpenRouter credentials.

Example:

```bash
export OPENROUTER_API_KEY=...
```

The credential is used when CLI runtime composition requires current OpenRouter
model state and executable OpenRouter model implementations.

It is not persisted as workflow configuration.

# AZATHOTH_BEDROCK

`AZATHOTH_BEDROCK` turns Amazon Bedrock on as a second provider (ADR 0103),
with the same values as `AZATHOTH_OTEL`: `1`, `true`, `yes` or `on`. It
needs the `bedrock` extra:

```bash
python -m pip install "azathoth-ai[bedrock]"
export AZATHOTH_BEDROCK=1
export AWS_REGION=us-east-1
export AZATHOTH_BEDROCK_PRICING=/path/to/bedrock-pricing.json
```

Azathoth reads no AWS credentials itself; boto3 finds them the way the AWS
CLI does. The region is `AWS_REGION`, then `AWS_DEFAULT_REGION`, then the
AWS profile's. `AZATHOTH_BEDROCK_PRICING` names the operator's pricing
document, since Bedrock reports no prices; a model it does not price has an
unknown cost. [Connecting Amazon Bedrock](../../../docs/bedrock.md) covers
credentials, the IAM policy and the pricing document.

`CliRuntimeConfiguration.bedrock_environment` keeps those four variables
when Bedrock is on, and is empty otherwise. They are read only when a
command composes the runtime, so a command that does not, such as
`tool list`, never imports boto3.

# AZATHOTH_CONTENT_STORE

An input given by reference is kept, by the digest of its bytes, in a
content store before its run starts (ADR 0096). The store is a table in the
database unless `AZATHOTH_CONTENT_STORE` names a bucket in Amazon S3, and a
prefix in it (ADR 0108). It needs boto3, from the `worker` extra:

```bash
python -m pip install "azathoth-ai[worker]"
export AZATHOTH_CONTENT_STORE=s3://azathoth-content/evidence
```

Content is kept at `<PREFIX>/sha256/<DIGEST>`, written only when nothing is
there yet, with S3's conditional `If-None-Match: *`, so it is never written
twice. Every command that stores content stores it there: `workflow run` and
`workflow invoke` with `--input-file`, `job run`, and the worker. The store
is opened only when a command first stores content, so a command that
stores none, such as `workflow list`, never imports boto3.

A store that cannot be used stops the command in one line, before anything
runs, and records nothing:

```text
AZATHOTH_CONTENT_STORE '/var/lib/azathoth/content' is not an s3://<BUCKET>[/<PREFIX>] URL.
AZATHOTH_CONTENT_STORE names S3, but boto3 is not installed; install azathoth-ai[worker].
Cannot store content in s3://<BUCKET>/<KEY>: <CODE>: <MESSAGE>
```

The store needs `s3:PutObject` and `s3:GetObject` under its prefix. The
worker opens it when it starts, so a store it cannot open stops it before it
receives anything.

A command that composes the runtime with Bedrock on prints one line to
stderr, and exits with status 1, when the extra is missing, no region is
configured, or the pricing document cannot be used:

```text
AZATHOTH_BEDROCK is set, but boto3 is not installed; install azathoth-ai[bedrock].
AZATHOTH_BEDROCK is set, but no AWS region is configured; set AWS_REGION.
AZATHOTH_BEDROCK_PRICING <PATH> is not a valid Bedrock pricing document: <REASON>.
```

# Tracing

`workflow run`, `workflow invoke`, `job run` and `worker run` are traced
with OpenTelemetry when `AZATHOTH_OTEL` is set and the `otel` extra is installed
(ADR 0100):

```bash
python -m pip install "azathoth-ai[otel]"
export AZATHOTH_OTEL=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

The rest is OpenTelemetry's standard `OTEL_*` configuration. Each command
exports one trace:

```text
job run            azathoth.job > azathoth.invocation > azathoth.run > azathoth.step
workflow invoke    azathoth.invocation > azathoth.run > azathoth.step
workflow run       azathoth.run > azathoth.step
```

Tracing is configured before a command does anything else. When it cannot
be, the command runs nothing, prints why on stderr and exits with status 1;
`job run` then prints no result at all:

```text
AZATHOTH_OTEL is set, but OpenTelemetry is not installed; install azathoth-ai[otel].
```

Spans are flushed before the command exits, and a backend that cannot be
reached never changes its exit status or stdout. Spans carry no content:
the telemetry README lists every span and attribute.

Other commands, benchmark runs and optimization among them, are not traced
in 1.1.

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

Runtime bootstrap reconstructs current provider model truth from every
provider that is on: OpenRouter when `OPENROUTER_API_KEY` is configured, and
Bedrock when `AZATHOTH_BEDROCK` is, in that order:

```text
OpenRouterModelDirectory    BedrockModelDirectory
        │                           │
        ▼                           ▼
ProviderModelObserver       ProviderModelObserver
        │                           │
        └─────────────┬─────────────┘
                      ▼
       ProviderModelCatalogSynchronizer
                      │
                      ▼
                 ModelCatalog
```

Provider observations are persisted separately from the current catalog.

With neither provider on, the current model catalog is empty.

A provider that is on but whose models cannot be discovered fails the
command, with one line on stderr and exit status 1. The catalog is never
composed without it:

```text
OpenRouter model discovery request failed.
Bedrock model discovery request failed: <AWS_ERROR_CODE>: <AWS_MESSAGE>.
```

# Executable Language Models

For each provider that is on, the CLI also builds executable language-model
implementations for its models in the current catalog, and composes them
into one registry.

```text
ModelCatalog
      +
OpenRouterConfiguration           BedrockClient
      │                                 │
      ▼                                 ▼
OpenRouterModelRegistryLoader     BedrockModelRegistryLoader
      │                                 │
      └────────────────┬────────────────┘
                       ▼
               LanguageModelRegistry
```

With neither provider on, the executable language-model registry is empty.

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

Import persists durable workflow intent as a new revision:

```text
Imported workflow <WORKFLOW_ID> revision 1.
```

Import never replaces anything. See "Workflow Revisions" below.

The document must declare a result. A document without one is rejected before
anything is saved:

```text
Workflow document must declare a result.
```

The command exits with status `1`.

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

Its single step declares an `answer` output, and the document declares that
output as the workflow result:

```json
"result": {
  "producer_step_id": "22222222-2222-2222-2222-222222222222",
  "name": "answer"
}
```

The result must name a step in the same document and an output that step
declares.

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

The command renders the latest revision by default, or the one named with
`--revision <NUMBER>`. It shows the revision, its import time and content
digest, workflow metadata, the declared result, and configured step
structure:

```text
ID: <WORKFLOW_ID>
Revision: 2 of 2
Imported: 2026-10-23T15:30:40+00:00
Content Digest: <SHA256>
Name: simple prompt
Version: 1.0.0
Description: Return a concise answer to one request.
Result: step <STEP_ID> output answer
Steps: 1
```

A name-only result renders as:

```text
Result: output answer (first producer in step order)
```

A workflow that declares an input or output schema (ADR 0118) shows it right
after its result:

```text
Result: output summary (first producer in step order)
Input Schema:
{
  "type": "object",
  "required": [
    "ticket"
  ]
}
Output Schema:
{
  "type": "string"
}
Steps: 2
```

`workflow production` shows the promoted workflow's schemas after its
deployment, since every invocation is checked against them: an input that
breaks the input schema fails with `invalid_input` before any run starts,
and a result that breaks the output schema fails with `invalid_output`, its
run kept, so `invocation show` names the run that produced it. Each
message names every violation by its JSON path, and the failure's metadata
lists them as `violations`:

```text
The workflow's input does not match its input schema: $: 'ticket' is a required property.
```

`workflow run` is not checked, so a workflow can be run while its contract
is still being written. A document whose
schema is not a JSON Schema is refused by `workflow import`, saying why:

```text
Workflow document is not a valid WorkflowSpecification. The workflow's input schema is not usable: A JSON Schema must be an object or a boolean.
```

A workflow stored before declared results existed renders:

```text
Result: undeclared
```

Such a workflow can still be inspected and run, but benchmarking, optimizing,
and promoting it fail until it is re-imported with a result.

It does not need to turn that specification into a `WorkflowCandidate` merely
to inspect it, and it reads durable state only, without provider credentials.

# Workflow Revisions

The workflow ID is a lineage. Every `workflow import` appends the next
revision under it; nothing is ever edited in place:

```text
workflow import v1.json   ──►  revision 1
workflow import v2.json   ──►  revision 2
workflow import v1.json   ──►  revision 3 (identical to revision 1)
```

To revert a workflow, import the earlier document again. The new revision
records the revert, and its output names the earliest revision with the same
content:

```text
Imported workflow <WORKFLOW_ID> revision 3 (identical to revision 1).
```

Content identity is a sha256 digest of the specification's canonical JSON, so
key order and formatting in the file do not matter.

List the revisions of one workflow, newest first, with:

```bash
azathoth workflow history <WORKFLOW_ID>
azathoth workflow history <WORKFLOW_ID> --limit <COUNT>
```

```text
3  2026-10-23T15:31:02+00:00  4f1a9c0e2b7d  1.0.0  simple prompt  identical to revision 1
2  2026-10-23T15:30:40+00:00  91d07a3c55e2  1.0.0  simple prompt
1  unknown                    4f1a9c0e2b7d  1.0.0  simple prompt
```

Each line contains the revision number, import time, the first twelve
characters of the content digest, the declared version, and the name.

Print any revision as a document `workflow import` accepts with:

```bash
azathoth workflow export <WORKFLOW_ID>
azathoth workflow export <WORKFLOW_ID> --revision <NUMBER> > workflow.json
```

Exporting and importing again appends a revision identical to the exported
one.

Execution always uses the latest revision:

```text
workflow run / workflow optimize / workflow promote / benchmark run / benchmark compare
    latest revision only
```

Only `show` and `export` take `--revision`. Running an older revision means
importing it again, so every execution traces to an import.

Every run records the revision it executed. `run show`, `experiment show`,
and `benchmark execution-show` render it as:

```text
Workflow Revision: 2
```

and production state records the revision that was promoted.

Workflows imported before revisions existed become revision 1 the first time
the database is opened. Their import time was never recorded, so it renders
as `unknown`, as do the revisions of records written before revisions.

An unknown workflow fails with `Workflow <WORKFLOW_ID> is not configured.`;
an unknown revision fails with:

```text
Workflow <WORKFLOW_ID> has no revision <NUMBER>.
```

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

`--input` supplies the run's external input as JSON:

```bash
azathoth workflow run <WORKFLOW_ID> --input '"the old ones wait"'
```

The run then starts with one `workflow.input.received` event, produced by
`azathoth.configured`, exactly as a benchmark case or a production invocation
would start it. `--input null` is input too: the event carries a JSON null.
Without `--input`, the run starts with an empty context, so a step bound to
the workflow input fails to resolve it.

`--input-file` supplies the input from a file instead; see
[Input Files](#input-files).

Only a run that received input can later become a benchmark case; see
[Add a Case From a Run](#add-a-case-from-a-run).

`--output` chooses what the operator sees; see
[Workflow Output Formats](#workflow-output-formats).

# Workflow Output Formats

`workflow run` and `workflow invoke` both take
`--output jsonl|text|result`. The default is `jsonl`.

| Format | stdout | stderr |
|---|---|---|
| `jsonl` | step records live, then one terminal record | nothing once execution starts |
| `text` | the human-readable report | step messages, one per line |
| `result` | the result value as JSON, or nothing when no result is declared | the error message |

Errors before execution starts, such as an unknown workflow or a candidate
that cannot be generated, are written to standard error as text in every
format.

## JSON Lines Records

Each line is one JSON object with a `type`:

```text
{"type": "step", "step_id": "<STEP_ID>", "message": "Counting words"}
{"type": "output", "step_id": "<STEP_ID>", "values": {"count": 4}}
{"type": "output", "step_id": "<STEP_ID>", "values": {"category": "billing", "confidence": 0.62}, "confidence": 0.62}
{"type": "result", "run_id": "<RUN_ID>", "value": 4}
{"type": "error", "run_id": "<RUN_ID>", "code": "workflow_execution_failed", ...}
```

- `step` is written when a step that declares a `message` starts.
- `output` is written when a step that sets `emit_values` succeeds. A step
  that declares a confidence (ADR 0098) also carries it as `confidence`.
- Failed and skipped steps write nothing after their `step` record.
- The stream ends with exactly one `result` or `error` record.

Lines are flushed as they are written, so a client can show progress live or
read only the last line. Concurrent steps interleave in the order they
actually start and finish. A `delta` record is reserved for streamed model
output.

`workflow run` terminal records carry `run_id`:

```text
{"type": "result", "run_id": "...", "value": ...}       declared result produced
{"type": "result", "run_id": "..."}                     no declared result
{"type": "error", "run_id": "...", "code": "workflow_execution_failed",
 "step_id": "...", "exception_type": "...", "message": "..."}   run halted
{"type": "error", "run_id": "...", "code": "result_not_produced", "message": "..."}
```

A run without a declared result omits `value`, so it cannot be mistaken for a
result of `null`. A halted run names the step that halted it and its actual
failure, because configured runs are the workflow author's tool.

`workflow invoke` terminal records carry `invocation_id` and the
caller-visible production error code and message, never a step's internal
failure:

```text
{"type": "result", "invocation_id": "...", "value": {"result": "Paris"}}
{"type": "error", "invocation_id": "...", "code": "workflow_not_deployed",
 "message": "The requested workflow is not deployed to production."}
```

## Result Output for Child Workflows

`--output result` prints only the result value as compact JSON, which is what
a tool that runs a child workflow reads:

```bash
azathoth workflow invoke <WORKFLOW_ID> \
    --input '"the old ones wait"' \
    --output result
```

```text
{"result": 4}
```

The child's step records never reach the parent: the parent only sees the
child's result.

`run_workflow`, from the standard tool library that `tool install-standard`
imports, is a ready-made tool that does this, and
`examples/workflows/count-words-in-child.json` uses it. The examples README
walks through running a child workflow. The tool reads `--output jsonl` and
keeps only the final record, so a failure also reports the child's invocation
ID.

## Child Lineage

A child records where it came from (ADR 0104). The step whose process tool
starts `azathoth` hands it its lineage in `AZATHOTH_LINEAGE`, which the
engine sets and no tool grants (see the tools README). `workflow run`,
`workflow invoke` and `job run` record it in the initial context of the run
or invocation they start, as a `workflow.lineage.received` event, one level
deeper than the step's own run:

```text
root run            depth 0
└── run_workflow ── child invocation       depth 1, parent: that step of the root run
                    └── run_workflow ── grandchild   depth 2, same root
```

A command started without `AZATHOTH_LINEAGE`, or with it empty, starts a
root and records no lineage, so everything run from a shell records exactly
what it always has.

Nesting is bounded by the engine at 8 levels below the root. A child that
would run deeper is refused before anything is resolved or recorded: no
input file is stored, and no invocation or run is saved. So is lineage that
is not valid. Each prints one line on stderr, writes nothing on stdout, and
exits with status 1:

```text
Workflow <WORKFLOW_ID> would run at depth 9, beyond the limit of 8 nested workflows.
AZATHOTH_LINEAGE is not valid lineage: step: Field required.
```

The tool that started the child reports that line as its step's failure, as
it reports any child failure. `invocation show` and `run show` name a
child's lineage.

## Children Under a Key

`workflow invoke` takes an idempotency key, and then runs the invocation
exactly as [`job run`](#run-a-job) runs a request under that key (ADR 0097):

```bash
azathoth workflow invoke <WORKFLOW_ID> --input <JSON> --idempotency-key <KEY>
```

The same request under the same key replays the recorded result, without
running anything, and reports it as the first invocation did. One that was
interrupted is resumed, once nothing runs it any more (ADR 0105). A key used
for another request, an invocation still running, and an input that cannot
be resolved end the output with an error record, carrying the job error's
`code` and `message`, or print the message on stderr in text, and exit with
status 1.

The standard composition tools, `run_workflow` 1.0.5 and `loop_workflow`
1.1.5, invoke every child under the key of the step attempt that starts it,
`azathoth:<RUN_ID>:<STEP_ID>:<ATTEMPT>`, and a loop under one key per
iteration, `azathoth:<RUN_ID>:<STEP_ID>:<ATTEMPT>:<ITERATION>`. So a parent
that is resumed reuses the children it already ran, and a loop resumed
halfway replays its finished iterations instead of running them again. A
retried attempt has a new number, and runs its children again. A child that
another process still runs is waited for, until the tool's timeout.

## The Children of a Run

A child is indexed under the run whose step started it, as soon as it
starts. List a run's children, oldest first, with:

```bash
azathoth run children <RUN_ID>
```

```text
Child Run ID: <RUN_ID>
Workflow ID: <WORKFLOW_ID>
Invocation ID: <INVOCATION_ID>
Parent Step ID: <STEP_ID> (attempt 1)
Status: succeeded
```

Children are separated by a blank line. A child that started but is not
recorded as finished is `unfinished`; one that ran no invocation names `no
invocation`. It lists the children of a run that never finished too. A run
that started none says so; one neither recorded nor journaled is not found,
and exits with status 1:

```text
Run <RUN_ID> started no children.
Run <RUN_ID> was not found.
```

`run show` names how many children a run started, after its lineage:

```text
Children: 2
```

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

A run that completes has succeeded, even when steps that tolerate failure
under `continue` or `skip_dependents` failed. A run fails only when it halts on
a `fail_workflow` step.

With `--output jsonl` or `--output result`, `workflow run` exits 0 when the
run ends in a `result` record, and 1 when it halted or did not produce its
declared result. With `--output text`, it exits 0 when the run succeeded.

Configuration or candidate-generation failures are emitted to standard error
and also return failure.

# Runs Journaled and Leased While They Execute

`workflow run`, `workflow invoke` and `job run` journal each run while it
executes, and hold its lease until it ends (ADR 0105). The lease lasts 60
seconds and is renewed every 15, so a command that is killed outright leaves
a run whose lease lapses within a minute.

A command stopped by Ctrl-C prints one line on stderr and exits with
status 130:

```text
Interrupted.
```

One stopped by SIGTERM, as a container runtime or a process supervisor
sends it, prints one line on stderr and exits with status 143:

```text
Terminated.
```

Either way the run stops where it is, releases its lease at once, and is not
recorded as a finished run: its journal shows how far it got. Nothing is
printed on stdout, and `job run` prints no envelope.

# Resume an Interrupted Run

A run that stopped before it finished resumes where it stopped, under the
same run ID (ADR 0105). A configured run, one `workflow run` started,
resumes with:

```bash
azathoth run resume <RUN_ID>
```

A production invocation, one `workflow invoke` or `job run` started, resumes
with:

```bash
azathoth invocation resume <INVOCATION_ID>
```

Each takes `--output` and reports the finished run exactly as the command
that started it would have, with the same exit status. A configured run
resumes from the specification revision it started from, and an invocation
from the production state that was active when it was created, so a newer
import or promotion never changes a run halfway. The steps of every layer
the run committed are reused, as are the attempts the interrupted layer
finished; an attempt in flight when the run stopped runs again.

`run show` does not show a run that never finished, because it is not
recorded yet. It says how to resume it, and exits with status 1:

```text
Run <RUN_ID> has not finished; resume it with azathoth run resume <RUN_ID>.
Run <RUN_ID> has not finished; resume it with azathoth invocation resume <INVOCATION_ID>.
```

Once finished, a run that was resumed names how often, after its lineage,
in `run show` and `invocation show`:

```text
Resumed: 1 time
```

`invocation show` names an incomplete invocation's run as soon as it starts.

Each refusal prints one line on stderr and exits with status 1, resuming
nothing:

```text
Run <RUN_ID> has already finished.
Run <RUN_ID> has no journal to resume.
Run <RUN_ID> executes invocation <INVOCATION_ID>; resume it with azathoth invocation resume <INVOCATION_ID>.
Run <RUN_ID> is still running (its lease expires at <TIME>).
Invocation <INVOCATION_ID> has already completed.
Invocation <INVOCATION_ID> was not found.
```

A run whose process was killed outright still holds its lease until it
lapses, within a minute; resume it after that.

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

Configured, benchmark, experiment, and production runs share one durable run
history. They are distinguished by association, not by separate storage:

```text
WorkflowRun associated with a ProductionInvocation
    production run

WorkflowRun observed by a WorkflowExperimentRecord
    experiment run

WorkflowRun recorded by a WorkflowBenchmarkExecutionRecord
    benchmark run

every other persisted WorkflowRun
    configured run
```

Production takes precedence over every other association, and experiment over
benchmark.

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
<RUN_ID>  2026-10-02T12:06:00+00:00  succeeded  0.700s  benchmark  -
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

A run started by a step of another run (see [Child Lineage](#child-lineage))
names its lineage right after its ID:

```text
Run ID: <RUN_ID>
Depth: 1
Parent Workflow ID: <WORKFLOW_ID>
Parent Run ID: <RUN_ID>
Parent Step ID: <STEP_ID> (attempt 1)
Root Workflow ID: <WORKFLOW_ID>
Root Run ID: <RUN_ID>
```

A step that declares a confidence (ADR 0098) names it after its strategy:

```text
Strategy: Classify ticket cheaply [<PROVIDER>/<MODEL>]
Confidence: 0.62
```

`workflow show` names the output a step reports as its confidence:

```text
Confidence Output: confidence
```

Each executed step also lists the resources its strategy bound:

```text
Resource: model openrouter/some-model
Resource: tool <IMPLEMENTATION_ID> (implementation_digest=<SHA256>, runtime=python, tool_id=<TOOL_ID>, tool_version=1.0.0)
```

Attributes are sorted by name. Structured attribute values render as compact
JSON.

A tool step's estimated cost is its children's, `$0.000000` for a tool that
starts none, since a tool calls no model (ADR 0117).

A tool binding records the content digest of the implementation that ran.
Implementation IDs stay stable across tool revisions while their source may
change, so the digest is what pins the exact code a run executed.

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

Feedback never becomes a benchmark case on its own. An operator turns a
corrected run into a case explicitly, with
[`benchmark add-case`](#add-a-case-from-a-run).

A corrected output of JSON null cannot be recorded: `--corrected-output null`
is treated as no correction. To capture a run whose correct answer is null,
pass `--expected null` to `benchmark add-case` instead.

# Empirically Optimize a Workflow

Run empirical workflow optimization against a durable benchmark with:

```bash
azathoth workflow optimize <WORKFLOW_ID> \
    --benchmark <BENCHMARK_ID> \
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

Each generation runs its candidates against the benchmark, ranks them, and
then proposes the next generation's candidates from its winner. Generation 1
runs the configured candidate and proposes cheaper model substitutions.
After the last generation, a final evaluation runs the population it
proposed (ADR 0091), so the default of 1 compares the configured models with
their cheaper substitutes. The final evaluation is skipped when the last
generation proposed no new candidate.

# Optimization Arguments

`--benchmark` is required and must be the UUID of a benchmark imported with
`benchmark import`.

`--target-latency` is required and is interpreted as seconds.

`--target-cost` is required and is interpreted as USD.

`--generations` sets how many generations propose candidates. Every
proposal is measured, by the next generation or by the final evaluation.

There is no `--expected` option. What counts as a correct answer belongs to
the benchmark's cases, each of which declares its own expected outcome and
comparison.

# Optimization Preconditions

Before loading the runtime, and therefore without provider credentials and
without executing any case, the command rejects:

```text
an unconfigured benchmark
    Benchmark dataset <BENCHMARK_ID> is not configured.

a benchmark with no cases
    Benchmark <BENCHMARK_ID> has no cases.

a semantic case while the judge rotation is empty
    Benchmark case <CASE_ID> uses comparison 'semantic', but no judges are configured.

a workflow without a declared result
    Workflow <WORKFLOW_ID> does not declare a result.
```

Each prints its message to standard error and exits with status `1`.

Once the runtime is loaded, and still before any candidate is generated, a
benchmark with semantic cases requires every judge in the rotation to be
authorized and currently available:

```text
Judge model <MODEL_IDENTIFIER> is not authorized.
Judge model <MODEL_IDENTIFIER> is not currently available.
```

A benchmark without semantic cases never checks the judges.

# Benchmark-Driven Judging

Every generation runs every candidate against every case of the benchmark.

For each case:

```text
case input
    │
    ▼
workflow.input.received event in the run's context
    │
    ▼
candidate run
    │
    ▼
declared result judged with the case's own comparison
```

Each candidate's per-case scorecards are averaged, dimension by dimension,
into one combined scorecard. That combined scorecard is what the ranking and
the model-substitution optimizer use, so a candidate wins by performing well
across the benchmark rather than on one example.

# Failed Runs Are Failed Cases

A candidate run that fails without producing its declared result does not
abort optimization and does not drop out of the ranking.

It is recorded with a `workflow-run-failure` evaluation:

```text
Reason: Workflow run failed at step <STEP_ID>: <failure message>
Evidence: expected = <expected value>
Evidence: failed_step_id = "<STEP_ID>"
Evidence: failure = {"exception_type": "...", "message": "..."}
```

The failed case scores zero quality, and it earns no latency or cost credit,
because failing quickly and cheaply is not efficiency. A candidate that
crashes therefore never outranks a correct one on speed or price alone.

A run whose steps failed but which still produced its declared result, for
example under the `continue` failure policy, is judged on that result like
any other run.

A generation in which every run failed still ranks and records normally.

# CLI Scoring Targets

The CLI constructs a workflow scoring policy from:

```text
target latency

target cost
```

These are scoring inputs used during the empirical workflow optimization
session.

A candidate whose cited steps kept their checks is scored on its citations
too, the fraction that verified, and renders a `Citations:` line after
`Cost:` in comparisons, experiments and optimization sessions; its overall
score is then the mean of five dimensions (ADR 0117).

They are not silently persisted as production policy by the CLI command.

# Optimization Lifecycle

Conceptually:

```text
configured WorkflowSpecification          durable BenchmarkDataset
        │                                         │
        ▼                                         │
runtime candidate generation                      │
        │                                         │
        ▼                                         │
for each candidate, for each case ◄───────────────┘
        │
        ├── execute with the case input
        └── judge the declared result with the case comparison
        │
        ▼
average per-case scorecards using latency / cost targets
        │
        ▼
rank empirical evidence
        │
        ▼
optimizer proposes next generation
        │
        ▼
final evaluation of the last proposals, when any are new
        │
        ▼
WorkflowOptimizationSession
```

The completed session is rendered to the operator.

# Optimization Final Evaluation

After the generations, the report shows the final evaluation in the same form
as a generation, then names the winning experiment:

```text
Generation 1
Experiment ID: <EXPERIMENT_ID>
Evaluated Candidates: 1
...
Next Population: 2

Final Evaluation
Experiment ID: <FINAL_EXPERIMENT_ID>
Evaluated Candidates: 2
Judge Calls: 0
Judge Cost: $0.000000
Winner:
...

Winning Experiment ID: <FINAL_EXPERIMENT_ID>
```

When the last generation proposed no new candidate, the final evaluation does
not run, and the report says so:

```text
Final Evaluation: not run. Generation 2 proposed no new candidates, so its winner is the session's winner.

Winning Experiment ID: <EXPERIMENT_ID>
```

The winning experiment's winner is the session's winner.

# Optimization Judge Cost

When any case is judged semantically, the session reports what judging cost.
The totals follow the summary, and each generation and the final evaluation
report their own, summed over every candidate they evaluated:

```text
Workflow: classify sentiment
Workflow ID: <WORKFLOW_ID>
Initial Candidates: 1
Generations: 2
Total Judge Calls: 9
Total Judge Cost: $0.001350

Generation 1
Experiment ID: <EXPERIMENT_ID>
Evaluated Candidates: 1
Judge Calls: 3
Judge Cost: $0.000450
Winner:
...
```

Without semantic cases every judge line reads zero.

Judging is the cost of evaluating candidates, and judges never run in
production, so judge calls and their cost never count against any candidate.
They stay out of every scorecard: a candidate's cost score comes from its own
runs only, and candidates rank exactly as they would without judging.

# Optimization Evidence Is Persisted

Every generation of `workflow optimize`, and its final evaluation, leaves
durable evidence:

```text
each candidate execution of each case
    WorkflowRun                 persisted, succeeded or failed
    WorkflowRunEvaluation       persisted, including run-failure evaluations

each generation, and the final evaluation
    WorkflowExperimentRecord    persisted
```

An experiment record names its benchmark and holds one observation per
candidate. Each observation has its own identity, the candidate signature,
the combined scorecard, and one case per benchmark case, in dataset order,
recording the case ID, run ID, evaluation ID, whether the case passed, and the
judge calls and cost spent judging it. The ranking lists observation IDs,
best first.

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
              Case ... run <RUN_ID> ──► run show / run feedback
```

Every run of an optimization candidate is observed by its experiment, so
`workflow runs` lists those runs with the `experiment` source.

# Records From Earlier Versions

Experiment records written before benchmark-driven optimization held a single
run and evaluation per observation, ranked by run ID.

They still decode and render. Each old observation becomes one case without a
case ID or a known outcome, and its observation ID is its old run ID, so the
old ranking still resolves. Old records have no benchmark.

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
<EXPERIMENT_ID>  2026-10-09T16:05:00+00:00  2 candidates  5 cases  winner <OBSERVATION_ID>  overall 0.900000
```

Each line contains the experiment ID, recorded time, candidate count, the
number of cases each candidate was judged on, winning observation, and winning
overall score. A record from an earlier version counts one case.

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
Benchmark: <BENCHMARK_ID>
Benchmark Digest: 4f1a9c0e2b7d
Candidates: 2
Cases: 2
Winner Observation ID: <OBSERVATION_ID>

Rank 1
Observation ID: <OBSERVATION_ID>
Workflow: summarize
Workflow ID: <WORKFLOW_ID>
Workflow Revision: 2
Strategy IDs: <STRATEGY_ID>
Passed: 1/2
Case <CASE_ID>: passed  run <RUN_ID>  evaluation <EVALUATION_ID>
Case <CASE_ID>: failed  run <RUN_ID>  evaluation <EVALUATION_ID>
Quality: 0.500000
Reliability: 1.000000
Latency: 0.950000
Cost: 0.800000
Overall: 0.812500
```

A scorecard rationale is rendered when one was recorded.

An observation whose cases were judged by judges ends with their totals,
after its scores and rationale:

```text
Overall: 0.812500
Judge Calls: 2
Judge Cost: $0.000300
```

Observations judged without judges, and records written before judge calls
were recorded, show no judge lines.

A record from an earlier version renders `Benchmark: none`,
`Passed: unknown`, and its one case as:

```text
Case none: unknown  run <RUN_ID>  evaluation <EVALUATION_ID>
```

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

The workflow must declare a result. Promoting a workflow without one fails
before anything is written:

```text
Workflow <WORKFLOW_ID> does not declare a result.
```

Promotion records one production emission, `result`, sourced from the
declared result. `workflow production` shows it:

```text
Emission: result <- step <STEP_ID> output answer
```

# Promote an Experiment's Winner

Promote the winner of an optimization experiment with:

```bash
azathoth workflow promote <WORKFLOW_ID> --experiment <EXPERIMENT_ID>
```

`<EXPERIMENT_ID>` is the `Winning Experiment ID` the optimize report ends
with. The experiment's top-ranked candidate is rebuilt, not trusted (ADR
0092):

```text
configured candidate of the current revision
        │
        ▼
each step whose strategy ID matches the winner's: kept
each other prompt step: matched among its candidates over authorized models
        │
        ▼
signature equals the winner's
        │
        ▼
explicit promotion
```

Promotion then pins every prompt step to the model it was measured on, exactly
as it does for the configured candidate.

Nothing is promoted, and the command exits with status 1, when:

```text
Experiment <EXPERIMENT_ID> was not found.

The candidate was measured on workflow <ID>, not workflow <WORKFLOW_ID>.

The candidate was measured on revision <N> of workflow <WORKFLOW_ID>, but its current revision is <M>.

Workflow step <STEP_ID> cannot be rebuilt: the model it was measured on is not currently available and authorized for it.
```

After importing a new revision, pin the winner's models in it deliberately,
or optimize it again. Either way, the new revision can be promoted without
`--experiment`. Deploying a workflow never requires optimizing it.

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

Exactly one of `--input`, which must be valid JSON, and `--input-file` is
required; see [Input Files](#input-files). `--output` chooses the
[output format](#workflow-output-formats), `jsonl` by default.

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

With `--output text`, on success, the CLI renders:

```text
Invocation ID: <INVOCATION_ID>
Status: succeeded
Result:
{
  "result": "Paris"
}
```

The workflow's declared result appears under the `result` key.

Production promoted before declared results existed returns `{}`. Promote the
workflow again to record the `result` emission.

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

A production run in which a redundant producer failed under `continue`, but
another produced the result, succeeds. It fails with
`Production workflow did not produce its declared result.` only when no
producer delivered the result.

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

# Inspect Active Production

Show what production currently executes for one workflow with:

```bash
azathoth workflow production <WORKFLOW_ID>
```

The rendering reads the current `WorkflowProductionState`, the execution
authority, and pairs it with the revision that recorded it:

```text
Workflow: summarize
Workflow ID: <WORKFLOW_ID>
Revision ID: <REVISION_ID>
Deployed At: 2026-10-09T17:00:00+00:00

Prompt Step: <STEP_ID>
Primary Model: openrouter/some-model
Substitute Models: openrouter/fallback-a, openrouter/fallback-b

Emission: result <- step <STEP_ID> output label
```

Every prompt step lists its primary model. `Substitute Models` appears only
for steps with approved substitutes. Emissions appear only when production
state declares them. Production promoted before declared results existed
shows no emission until the workflow is promoted again.

The active revision is the most recent revision whose recorded state equals
the current production state. It is not simply the newest revision.

State written before revisions were recorded has no matching revision and
renders:

```text
Revision ID: unrecorded
Deployed At: unknown
```

Production state is shown even when the workflow has since been removed from
configuration, because production state, not configuration, is what
`workflow invoke` executes.

A configured workflow that was never promoted fails with:

```text
Workflow <WORKFLOW_ID> is not in production.
```

An identifier that is neither configured nor in production fails with:

```text
Workflow <WORKFLOW_ID> is not configured.
```

# List Production Revisions

List the production revision history of one workflow with:

```bash
azathoth workflow revisions <WORKFLOW_ID>
```

Limit the listing to the most recent revisions with:

```bash
azathoth workflow revisions <WORKFLOW_ID> --limit <COUNT>
```

`--limit` must be a positive integer.

Revisions are listed newest first, one line per revision:

```text
<REVISION_ID>  2026-10-09T17:10:00+00:00  -       openrouter/model-c
<REVISION_ID>  2026-10-09T17:05:00+00:00  active  openrouter/model-b
<REVISION_ID>  2026-10-09T17:00:00+00:00  -       openrouter/model-a
```

Each line contains the revision ID, creation time, an active marker, and the
primary model of every prompt step. Workflows without prompt steps show
`no prompt steps`.

The `active` marker follows the same rule as `workflow production`: it marks
the revision matching current production state, which need not be the newest.

The limit is applied after sorting.

A configured workflow with no revisions prints nothing and exits
successfully.

Revisions of a workflow since removed from configuration remain listable.

An identifier that is neither configured nor present in revision history
fails with:

```text
Workflow <WORKFLOW_ID> is not configured.
```

Revision history is audit evidence. Listing it never changes what production
executes.

# List Production Invocations

List production invocations of one workflow with:

```bash
azathoth workflow invocations <WORKFLOW_ID>
```

Limit the listing to the most recent invocations with:

```bash
azathoth workflow invocations <WORKFLOW_ID> --limit <COUNT>
```

`--limit` must be a positive integer.

Invocations are listed newest first, one line per invocation:

```text
<INVOCATION_ID>  2026-10-09T17:10:00+00:00  pending                       no run
<INVOCATION_ID>  2026-10-09T17:05:00+00:00  timeout                       no run
<INVOCATION_ID>  2026-10-09T17:00:00+00:00  succeeded                     <RUN_ID>
```

Each line contains the invocation ID, creation time, outcome, and the
associated workflow run.

The outcome is one of:

```text
succeeded
    a successful result was recorded

<error code>
    a failure was recorded, for example invalid_input or timeout

pending
    no terminal result was recorded
```

Invocations that never produced a workflow run show `no run`.

The limit is applied after sorting.

A configured workflow with no invocations prints nothing and exits
successfully.

Invocations of a workflow since removed from configuration remain listable.

An identifier that is neither configured nor present in invocation history
fails with:

```text
Workflow <WORKFLOW_ID> is not configured.
```

# Show an Invocation

Inspect one production invocation with:

```bash
azathoth invocation show <INVOCATION_ID>
```

The invocation is rendered with its caller-visible evidence:

```text
Invocation ID: <INVOCATION_ID>
Workflow ID: <WORKFLOW_ID>
Created At: 2026-10-09T17:00:00+00:00
Outcome: succeeded
Run ID: <RUN_ID>
Caller Metadata:
{
  "caller": "billing-service"
}
Input:
{
  "text": "hello"
}
Result:
{
  "answer": "OK"
}
```

`Caller Metadata` appears only when metadata was recorded. `Input` is the
payload the caller supplied to `workflow invoke`.

An input that has provenance is followed by it: one given by reference, such
as `--input-file` or a worker's `s3://`, and an inline job input that holds
a document or names an origin (ADR 0112). An `s3://` input names the object
version it was read from:

```text
Input Provenance:
{
  "uri": "s3://claims-intake/2026/11/claim-0412.pdf",
  "origin": {
    "uri": "s3://claims-intake/2026/11/claim-0412.pdf",
    "version_id": "3HL4kqtJlcpXroDTDmJ.rmSpXd3dIbrHY",
    "etag": "9b2cf535f27731c974343645a3985328"
  },
  "media_type": "application/pdf",
  "size_bytes": 482113,
  "digest": "<SHA-256>"
}
```

An invocation started by [`job run`](#run-a-job) also names its idempotency
key and request digest, right after `Run ID`:

```text
Run ID: <RUN_ID>
Idempotency Key: order-4711-review
Request Digest: <SHA-256>
```

An invocation started by a step of another run (see
[Child Lineage](#child-lineage)) then names its lineage, as `run show` does:
its depth, the parent workflow, run and step with the step's attempt, and the
root workflow and run.

A failed invocation renders its message and optional metadata instead of a
result:

```text
Outcome: timeout
Run ID: no run
...
Message: Workflow timed out.
```

A pending invocation renders neither.

An invocation whose run had [cited steps](../workflows/README.md#cited-prompt-steps)
ends with every check they kept (ADR 0116). Each step names its record in
the content store, then each check, in the order its reply held them: the
status, the source, the segment, and the quote. A provider's own citation
also names its pages, and one that no segment verified names `-` for its
segment:

```text
Citations:
Step <STEP_ID>: 2 citations, record <SHA-256>
  verified claim p1.s2 'December 14'
  quote_not_found claim p2.s1 'Denied.'
```

With `--links`, each verified check is followed by a link to its page in
its document (ADR 0117):

```bash
azathoth invocation show <INVOCATION_ID> --links
```

```text
  verified claim p1.s2 'December 14'
    https://claims-intake.s3.amazonaws.com/2026/11/claim-0412.pdf?versionId=<VERSION_ID>&...#page=1
```

The link is made by the resolver of the document's origin: an `https`,
`http` or `file` origin is the link, with `#page=N` from the check's PDF
fragment; an `s3://` origin becomes a presigned GET of the object version
the run read, signed with your AWS credentials and valid for
`AZATHOTH_LINK_EXPIRY_SECONDS`, one hour by default and seven days at
most. A document with no origin, or of another scheme, has no link. Links
expire, so they are made each time and never kept. These fail the command:

```text
AZATHOTH_LINK_EXPIRY_SECONDS must be a whole number of seconds from 1 to 604800, not '<VALUE>'.
Links to s3:// documents need boto3, which is not installed; install azathoth-ai[worker].
A link to <URI> could not be signed: <REASON>
```

A record the content store no longer holds is named as such:

```text
Step <STEP_ID>: record <SHA-256> is not in the content store.
```

Content under a record's digest that is not a record of checks fails the
command:

```text
Content <SHA-256> is not a record of citation checks.
```

# Export Citations as Web Annotations

Every verified citation a run's cited steps kept exports as W3C Web
Annotations (ADR 0117), for a run or for the run of an invocation:

```bash
azathoth run annotations <RUN_ID>
azathoth invocation annotations <INVOCATION_ID>
```

The output is one JSON-LD `AnnotationCollection`, its one `AnnotationPage`
holding an `Annotation` per verified check: `highlighting` the place its
anchor names, with the anchor's selectors as they are, its source the
document's origin, with the S3 object version when one was recorded, or
the document's digest as an RFC 6920 `ni:` URI. A check that did not
verify is left out, and the collection's label counts it. The same checks
always export to the same bytes, so an export can be diffed and kept
beside the run it came from:

```text
"label": "Citations of run <RUN_ID>: 1 verified, 1 not verified and left out.",
"target": {"type": "SpecificResource", "source": "s3://claims-intake/2026/11/claim-0412.pdf?versionId=<VERSION_ID>", "selector": [...]}
```

Only durable state is read, and a run still under way exports what its
committed steps checked. These fail:

```text
Run <RUN_ID> was not found.
Invocation <INVOCATION_ID> was not found.
Invocation <INVOCATION_ID> has no run.
Citation record <DIGEST> of step <STEP_ID> is not in the content store.
Content <DIGEST> is not a record of citation checks.
```

The `Run ID` continues into run inspection:

```bash
azathoth run show <RUN_ID>
```

An unknown invocation fails with:

```text
Invocation <INVOCATION_ID> was not found.
```

`workflow production`, `workflow revisions`, `workflow invocations`, and
`invocation show` read durable state only. They do not require provider
credentials or runtime bootstrap.

# Run a Job

`job run` invokes a production workflow from a versioned job request, and
prints the result as a versioned job result (ADR 0097):

```bash
azathoth job run request.json
azathoth job run - < request.json
```

It is the typed job API that programs share, and the queue worker,
Azathoth-MCP and the UI will speak it too. Unlike `workflow invoke`, a
request names everything in one document, and carries an idempotency key, so
it can be retried safely.

## Job Requests

A request is one JSON object:

```json
{
  "kind": "invoke",
  "version": 1,
  "idempotency_key": "order-4711-review",
  "workflow_id": "d2000000-0000-4000-8000-000000000010",
  "input": {"value": {"title": "Rename total to order_total"}},
  "caller_metadata": {"ticket": "OPS-12"}
}
```

- `kind` is `invoke` and `version` is `1`; both are required.
- `idempotency_key` is required: 1 to 255 characters, with no control
  characters.
- `input` is an inline value or a reference. Like `--input-file`, `job run`
  resolves only `file://` references, which must be absolute:
  `{"uri": "file:///Users/you/change.json", "media_type": "application/json"}`.
  A reference is resolved, capped and stored exactly as an input file is
  (see [Input Files](#input-files)).
- `caller_metadata` is optional, and is recorded with the invocation.

No other key is accepted.

## Job Results

`job run` prints exactly one result, as one line of JSON on stdout, and
nothing else, whatever the request. There are three exceptions, all
configuration that is wrong for every request alike, and in each the command
prints no result, only its error on stderr, and exits with status 1:

- tracing that cannot be configured (see [Tracing](#tracing)), found before
  the request is read;
- a PostgreSQL database that cannot be used, because the `postgres` extra is
  missing or its schema is not this Azathoth's (see
  [AZATHOTH_DATABASE](#azathoth_database)), found once a valid request is
  read. A request that cannot be read or decoded is still rejected with a
  result, since it never reaches the database;
- a provider that cannot be used: Bedrock without its extra, its region or a
  usable pricing document, or any provider whose models cannot be discovered
  (see [Current Provider Models](#current-provider-models)), found when the
  job first needs the runtime. A job that is replayed, conflicts or is
  rejected never composes it, so it still gets its result;
- a job started by a step of another run whose lineage is not valid, or
  that would be nested too deeply (see [Child Lineage](#child-lineage)),
  found once a valid request is read, before anything is replayed, resolved
  or recorded.

```json
{"kind": "invoke", "version": 1, "idempotency_key": "order-4711-review", "status": "succeeded", "replayed": false, "invocation_id": "<INVOCATION_ID>", "result": {"result": {"verdict": "approve"}}, "error": null}
```

`result` is what production emits, exactly as `workflow invoke --output
result` prints it.

| Status | Meaning |
| --- | --- |
| `succeeded` | The invocation completed; `result` holds what production emits. |
| `failed` | The invocation completed with a production failure. |
| `rejected` | No invocation was recorded: the request, its version or its input was refused, or its key was already used for a different request. |
| `incomplete` | The key's invocation exists but has no result: it was interrupted, or is still running. |

A job that did not succeed carries an `error` with a `code`, a `message` and
`metadata`. A failed job carries the same code `workflow invoke` reports,
such as `workflow_not_deployed` or `timeout`, or `invalid_input` and
`invalid_output` when the promoted workflow's input or output schema was
broken (ADR 0118). A rejected one carries
`invalid_request`, `unsupported_version`, `idempotency_conflict` or
`invalid_input`. An unsupported version names the versions that would be
accepted:

```json
{"code": "unsupported_version", "message": "Job version 2 is not supported; supported versions: 1.", "metadata": {"supported_versions": [1]}}
```

A request file that cannot be read, or is not JSON, is still answered with a
rejected result.

## Job Exit Status

`job run` exits with status 0 when the job `succeeded`, and 1 for every other
status. The result on stdout says why.

## Retrying Jobs

A request sent again with the same key and the same content does not run
again. It reports the recorded invocation, with `"replayed": true`:

- a finished invocation replays as `succeeded` or `failed`;
- an invocation without a result that another process still runs is
  `incomplete`;
- an invocation without a result that nothing runs any more, because the
  process running it was stopped, or killed and its lease has lapsed, is
  resumed where its run stopped (ADR 0105). Its result is reported as if it
  had just run, with `"replayed": false`, and is replayed from then on;
- an invocation that the process still running it finishes while the
  request is being looked up replays the result that process recorded.

Failures replay too: a key always reports the same outcome. Send a new key to
try again.

The same key with different content, another input, another workflow or
other caller metadata, is rejected as `idempotency_conflict`. Key order and
formatting do not matter; the request is compared by its canonical form.

A rejected request records nothing, so its key may be sent again once the
request is fixed. Keys never expire in 1.1.

## Jobs Load the Runtime Only to Invoke

The database is opened only for a request that decodes, and the runtime,
with any provider credential, is composed only when a workflow is actually
invoked. A replay, a conflict or a rejection needs no credentials.

`job run` streams no step records. A job is a request and a response; use
`workflow invoke --output jsonl` to watch steps live.

# Run a Worker

`worker run` takes job requests from an Amazon SQS queue and runs them, one
at a time, until it is stopped (ADR 0107). It needs the `worker` extra:

```bash
python -m pip install "azathoth-ai[worker]"
azathoth worker run --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/azathoth-jobs
```

Without it, the worker runs nothing and says so:

```text
azathoth worker needs boto3, which is not installed; install azathoth-ai[worker].
```

Each message's body is exactly one job request, as `job run` reads it, and
it is answered as `job run` answers it: a key it has seen replays, an
interrupted invocation resumes, and anything else runs. The result settles
the message:

| Result | Message |
| --- | --- |
| `succeeded`, `failed`, `rejected` | Sent to the result queue, when there is one, then deleted. |
| `incomplete` | Left on the queue. It comes back when its visibility timeout runs out, and is resumed once its run's lease has lapsed. |

A worker that dies with a message leaves it to come back the same way, so
another worker resumes its run from the journal (ADR 0105).

## Worker Inputs

A request's `input` may be an `s3://` reference to an object inside a
location the worker allows, and nothing else (ADR 0108). A location is a
bucket, or a bucket and a key prefix:

```bash
azathoth worker run --queue-url <QUEUE_URL> --allow-input-bucket azathoth-inputs/requests/
```

```json
{"input": {"uri": "s3://azathoth-inputs/requests/review.json", "media_type": "application/json"}}
```

The object is read before the run starts, never more than `--max-input-bytes`
of it, decoded as the request's media type, and kept in the content store by
its digest; the run records where it came from, as for an input file. Each
input the worker may not use is `rejected` as `invalid_input`, so its
message is deleted rather than received again:

```text
Input s3://azathoth-inputs/secrets/key.json is not in an allowed location; allowed: azathoth-inputs/requests/.
Input s3://azathoth-inputs/requests/review.json does not exist.
Unable to read input s3://azathoth-inputs/requests/review.json: AccessDenied: Access Denied
Input s3://azathoth-inputs/requests/review.json is larger than the limit of 10485760 bytes.
```

A prefix is matched literally, as S3 matches it: end it with `/` to allow
one folder and not its namesakes. A worker allowed no location accepts no
reference at all, and none ever accepts `file://`, so a message can never
read the worker's own disk:

```text
Input file:///etc/hostname uses the 'file' scheme, which is not accepted here; no schemes are accepted.
```

S3 that cannot be reached, as without credentials, is not the request's
fault: it stops the worker, and the message stays on the queue, as any other
failure of the worker does. A worker allowed a location needs boto3 before it
receives anything:

```text
s3:// inputs need boto3, which is not installed; install azathoth-ai[worker].
```

The cap is for content the engine resolves into a run. Data larger than
that goes by pointer: a request's inline value names the object,
`split_s3_object` streams it into chunk objects, `map_workflow` runs a
child over the chunks, and each child reads its own with `read_s3_object`
(ADR 0106, ADR 0108, ADR 0110).

## Worker Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--queue-url` | required | The SQS queue job requests come from, standard or FIFO. |
| `--result-queue-url` | none | A standard SQS queue every final result is sent to. |
| `--wait-seconds` | 20 | How long one receive waits for a message, at most 20. |
| `--visibility-timeout-seconds` | 120 | How long a received message stays hidden, at most 43200. |
| `--extend-every-seconds` | 30 | How often a running job's message is hidden again. |
| `--heartbeat-file` | none | A file to touch while the worker is alive. |
| `--allow-input-bucket` | none | A bucket, or `BUCKET/PREFIX`, `s3://` inputs may come from; may be given more than once. |
| `--max-input-bytes` | 10485760 | The largest input to read, at most 104857600 (100 MiB). |

Settings that are not valid are refused before anything is opened, one line
per option:

```text
--wait-seconds: Input should be less than or equal to 20.
A worker must extend a message's visibility more often than its visibility timeout of <SECONDS> seconds.
--allow-input-bucket: 'Not_A_Bucket' is not an S3 bucket, or a bucket and a key prefix: a bucket name is 3 to 63 lowercase letters, digits, dots and hyphens.
--max-input-bytes: Input should be from 1 to 104857600 bytes.
```

A result sent to the result queue is the one line `job run` prints, with the
request's key in the `idempotency_key` message attribute. A FIFO result
queue is refused:

```text
The result queue <URL> is a FIFO queue; the worker sends results to standard queues only.
```

The client uses AWS's own credential chain. The region is the one the queue
URL names; a URL of another host, such as a local stand-in for SQS reached
through `AWS_ENDPOINT_URL_SQS`, takes `AWS_REGION`:

```text
Cannot tell the AWS region of queue <URL>; set AWS_REGION.
```

The worker needs `sqs:ReceiveMessage`, `sqs:DeleteMessage` and
`sqs:ChangeMessageVisibility` on its queue, `sqs:SendMessage` on the result
queue, and `s3:GetObject` on the objects under each allowed location. Without
`s3:ListBucket` on a bucket, S3 answers `AccessDenied` for a missing object
there rather than saying it does not exist.

## Worker Output

Each settled message is one line of JSON on stdout:

```json
{"message_id": "059f36b4-87a3-44ab-83d2-661975830a7d", "idempotency_key": "order-4711-review", "status": "succeeded", "invocation_id": "5b0c2a52-0000-4000-8000-000000000001", "settled": "deleted"}
```

`settled` is `deleted`, `left` or `returned`. A message handed back has a
`null` status and invocation.

With tracing on, each job is traced as `job run` traces it, and its job span
carries `azathoth.worker.message_id`.

## Stopping a Worker

The first Ctrl-C or SIGTERM drains the worker. It prints `Stopping.`, lets a
receive in progress finish, stops the job running, which releases its run's
lease, and makes its message visible again at once, so another worker
resumes the run without waiting out the timeout. It then prints `Stopped.`
and exits with 0. A drain takes at most one receive wait and the time a job
takes to unwind, so give it more than 20 seconds before it is killed.

A second signal stops it where it is: Ctrl-C exits with 130 and prints
`Interrupted.`, SIGTERM exits with 143 and prints `Terminated.`. Its message
comes back when its visibility timeout runs out.

A queue that refuses a call, or a job that cannot run at all, as when the
database is unreachable, stops the worker with status 1 and the reason on
stderr. The message it was running stays on the queue:

```text
SQS ReceiveMessage failed on <URL>: <CODE>: <MESSAGE>
Message <MESSAGE_ID> stays on the queue; running it failed: <REASON>
```

A request that does not decode is not one of these: it is `rejected`, and
deleted. A message that keeps stopping workers is the queue's to move aside:
give the queue a dead-letter queue.

## Worker Health

With `--heartbeat-file`, the worker touches the file before every receive
and after every extension. `worker health` exits with 0 when the file is
younger than `--max-age-seconds` (90 by default), and 1 when it is not, so it
serves as a container's health check:

```bash
azathoth worker health --heartbeat-file /tmp/azathoth-heartbeat
```

```text
The last heartbeat at /tmp/azathoth-heartbeat is 4 seconds old.
The last heartbeat at /tmp/azathoth-heartbeat is 131 seconds old, older than 90 seconds.
No heartbeat at /tmp/azathoth-heartbeat; the worker has not started, or cannot write it.
```

A heartbeat file the worker cannot write stops it before it receives
anything:

```text
Cannot write the heartbeat file <PATH>: <REASON>.
```

One that stops being writable while a job runs is reported on stderr, and
the job finishes; the next receive's heartbeat then stops the worker, and
until then the health check finds the file going stale.

# No Dedicated Rollback Command in V1

V1 does not expose:

```text
azathoth workflow rollback
```

Production changes remain explicit promotions.

Production revision history is inspectable with `workflow revisions`, but no
command executes or restores a historical production revision.

To return to earlier workflow content, export or locate the earlier
specification revision with `workflow history` and `workflow export`, import
it again, and promote it explicitly.

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

# Deauthorization Is Guarded by the Judge Rotation

A model in the semantic judge rotation cannot be deauthorized, even with
`--force`, because every judge must be authorized:

```text
Model 'openrouter/some-model' is a semantic judge and was not deauthorized.
Remove it from the rotation first with: azathoth judge remove openrouter/some-model
```

The rotation is checked before production dependents.

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
├── install-standard
├── list
├── show
├── history
├── export
├── from-mcp
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

`tool import` rejects a document whose implementations use a runtime Azathoth
cannot execute, before anything is saved:

```text
Tool implementation <ID> uses unsupported runtime 'javascript'; supported runtimes: mcp, process, python.
```

`tool implementation-show` renders a process implementation's command,
timeout and environment grants alongside its runtime:

```text
Runtime: process
Entrypoint: run
Command: python
Timeout: 30 seconds
Environment: AZATHOTH_DATABASE, OPENROUTER_API_KEY, AZATHOTH_OTEL
```

A process tool sees only the platform's base variables and the ones it
grants itself, never Azathoth's whole environment (ADR 0099). `Environment`
appears only when an implementation grants something; the tools README
lists the base variables.

An MCP implementation has no source, command or entrypoint; it is rendered
with the server, the remote tool, the schema digest it is pinned to and, for
an HTTP server, the variable holding its bearer token, never its value
(ADR 0119):

```text
Runtime: mcp
Timeout: 20 seconds
MCP Server: https://mcp.example.com/mcp
MCP Tool: search
Schema Digest: <SCHEMA_DIGEST>
Authorization: SEARCH_TOKEN
```

`tool verify` runs every implementation through the runtime it declares, so
process and MCP tools are verified against their test cases exactly like
Python tools.

# Tool Revisions

A tool document bundles one exact definition version with its
implementations and test cases. Every `tool import` appends the next revision
of that `<TOOL_ID>@<VERSION>`; nothing is ever rejected for already existing:

```text
Imported tool <TOOL_ID>@1.0.0 revision 2.
Imported tool <TOOL_ID>@1.0.0 revision 3 (identical to revision 1).
```

The latest revision of each version defines the current artifacts that
workflows resolve and `tool show`, `implementations`, and `test-cases` list.
An implementation or test case the previous revision held and the new one
drops is no longer current, unless the latest revision of another version of
the same tool still holds that test case. Re-importing an earlier document
restores its artifacts exactly.

A document is rejected, with nothing saved, when its tool ID is already saved
under another name, in any version, when an implementation ID belongs to
another tool or another version, or when a test case ID belongs to another
tool:

```text
Tool <TOOL_ID> is named '<NAME>'; a document cannot rename it to '<NEW_NAME>'.
Tool implementation <IMPLEMENTATION_ID> belongs to tool <TOOL_ID>@<VERSION>.
Tool test case <TEST_CASE_ID> belongs to tool <TOOL_ID>.
```

A tool's name is the capability workflows require, so a document never
renames one: a different tool that reuses an ID needs an ID of its own.

List every version's revisions, newest first, with:

```bash
azathoth tool history <TOOL_ID>
azathoth tool history <TOOL_ID> --version <VERSION> --limit <COUNT>
```

```text
2.0.0  1  2026-10-23T15:52:10+00:00  7c21e0a94f3b  1 implementations  1 test cases
1.0.0  3  2026-10-23T15:51:58+00:00  4f1a9c0e2b7d  1 implementations  1 test cases  identical to revision 1
```

Print any revision of one version as an importable document with:

```bash
azathoth tool export <TOOL_ID> --version <VERSION>
azathoth tool export <TOOL_ID> --version <VERSION> --revision <NUMBER>
```

Tool versions saved before revisions existed become revision 1 of their
version, without an import time. Test cases belong to a tool rather than to
one version, so each such revision holds every test case of its tool.

# Write an MCP Tool's Document

`tool from-mcp` lists the tools one MCP server serves and prints the named
tool's document, its implementation pinned to the digest of the tool's
schemas as they are served now (ADR 0119). Name a server reached over HTTP
by its URL, or give the command that starts a stdio server after `--`:

```bash
azathoth tool from-mcp --tool <NAME> --url <URL> [--authorization <VARIABLE>] [--timeout-seconds <SECONDS>]
azathoth tool from-mcp --tool <NAME> [--grant <VARIABLE>]... [--timeout-seconds <SECONDS>] -- <COMMAND>...
```

| Option | Meaning |
| --- | --- |
| `--tool` | The name the server lists the tool under. |
| `--url` | The URL of a server reached over streamable HTTP. |
| `--authorization` | The variable holding an HTTP server's bearer token. |
| `--grant` | A variable a stdio server is given, or a prefix ending in `*`. Repeatable. |
| `--timeout-seconds` | How long each call may take; also how long listing may take now, 30 seconds when not given. |

Nothing is stored: import the document with `tool import`. Its tool and
implementation IDs are derived from the server, the tool and the pin, so a
tool whose schemas changed is written as a new implementation of the same
tool. A binding no implementation may declare is refused with the same
message an import would give, and so is a server that is named both ways or
not at all:

```text
Name the MCP server with --url or with a command after --, not both.
Name the MCP server with --url, or with a command after --.
MCP server <SERVER> serves no tool named <TOOL>.
```

The [MCP tools guide](../../../docs/mcp-tools.md) walks through writing,
importing and calling one.

# Install the Standard Tools

Azathoth ships a standard tool library inside the package (ADR 0095):

```text
run_workflow     1.0.0   run a child workflow once
loop_workflow    1.1.0   run a child workflow repeatedly
map_workflow     1.0.0   run a child workflow per item of a list
json_select      1.0.0   select one value from JSON by path
json_object      1.0.0   build one object from a step's inputs
json_merge       1.0.0   deep-merge one object into another
validate_json    1.0.0   check a value against a JSON Schema
chunk_text       1.0.0   split text into chunks of a size
join_text        1.0.0   join strings, or rendered objects, into one text
render_template  1.0.0   render a text template from a step's inputs
split_s3_object  1.0.0   split an S3 object into chunk objects
read_s3_object   1.0.0   read and decode one S3 object within a cap
```

The [standard tool library](../standard/README.md) describes each tool's inputs, outputs
and failures.

Install it into the configured database with:

```bash
azathoth tool install-standard
```

```text
Installed tool run_workflow@1.0.0 revision 1.
Installed tool loop_workflow@1.1.0 revision 1.
Installed tool map_workflow@1.0.0 revision 1.
Installed tool json_select@1.0.0 revision 1.
Installed tool json_object@1.0.0 revision 1.
Installed tool json_merge@1.0.0 revision 1.
Installed tool validate_json@1.0.0 revision 1.
Installed tool chunk_text@1.0.0 revision 1.
Installed tool join_text@1.0.0 revision 1.
Installed tool render_template@1.0.0 revision 1.
Installed tool split_s3_object@1.0.0 revision 1.
Installed tool read_s3_object@1.0.0 revision 1.
Installed tool segment_pdf@1.0.0 revision 1.
```

For each standard document, in that order, the command compares its content
digest with the latest revision of the same exact tool version:

- a version that is not in the database is imported as revision 1;
- a version whose latest revision has the same digest is left alone, and
  nothing is written:

  ```text
  Tool loop_workflow@1.1.0 is already installed (revision 1).
  ```

- a version whose latest revision differs, for example an operator's modified
  copy, gets the standard document as its next revision, which becomes
  current. When that content matches an earlier revision, it says so, as
  `tool import` does:

  ```text
  Installed tool loop_workflow@1.1.0 revision 3 (identical to revision 1).
  ```

Nothing is edited in place, so the command is always safe to run again. The
first document that cannot be saved, because its tool ID holds another tool
or an implementation ID in it belongs to another tool or version, stops the
installation with the same message as `tool import`, and the command exits
with status 1. The documents before it stay installed.

A new Azathoth release may ship new versions of standard tools. Running the
command after upgrading adds them beside the old ones, and workflows keep
the exact versions they require. `azathoth init` runs the same installation.

Azathoth 1.1 also ships new revisions of `run_workflow@1.0.0` and
`loop_workflow@1.1.0` that grant the environment their child process needs
(ADR 0099), including the tracing configuration (ADR 0100). A database that
installed them from a development build of 1.1, before ADR 0099, runs child
workflows only after the command runs again, which also installs the tools
added since; a database from the 1.0 release upgrades as the
[changelog](../../../CHANGELOG.md#upgrading-from-10) shows:

```text
Installed tool run_workflow@1.0.0 revision 2.
Installed tool loop_workflow@1.1.0 revision 2.
Installed tool map_workflow@1.0.0 revision 1.
Installed tool json_select@1.0.0 revision 1.
Installed tool json_object@1.0.0 revision 1.
Installed tool json_merge@1.0.0 revision 1.
Installed tool validate_json@1.0.0 revision 1.
Installed tool chunk_text@1.0.0 revision 1.
Installed tool join_text@1.0.0 revision 1.
Installed tool render_template@1.0.0 revision 1.
Installed tool split_s3_object@1.0.0 revision 1.
Installed tool read_s3_object@1.0.0 revision 1.
Installed tool segment_pdf@1.0.0 revision 1.
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

# Judge Commands

Semantic benchmark cases are judged by a durable rotation of language-model
judges. The `judge` command family operates that rotation:

```bash
azathoth judge add <MODEL_IDENTIFIER>
azathoth judge list
azathoth judge remove <MODEL_IDENTIFIER>
```

# Add a Judge

```bash
azathoth judge add <MODEL_IDENTIFIER>
```

appends one model to the end of the rotation:

```text
Added judge <MODEL_IDENTIFIER>.
```

Judges see benchmark data, so a judge must be a model the organization has
authorized, exactly like any model a workflow may select. Adding loads the
runtime and requires the model to be currently available and authorized:

```text
Model '<MODEL_IDENTIFIER>' is not currently available.
Model '<MODEL_IDENTIFIER>' is not authorized.
Judge '<MODEL_IDENTIFIER>' is already in the rotation.
```

A rotation of one judge is valid.

# List and Remove Judges

```bash
azathoth judge list
```

prints the rotation in order, one identifier per line, and prints nothing for
an empty rotation.

```bash
azathoth judge remove <MODEL_IDENTIFIER>
```

removes one judge:

```text
Removed judge <MODEL_IDENTIFIER>.
Judge '<MODEL_IDENTIFIER>' is not in the rotation.
```

`judge list` and `judge remove` read and write durable state only. They need
no provider credentials, so a judge whose model is no longer available can
still be removed.

# How Judges Are Used

Each semantic case is assigned a first judge by a stable hash of its
expectation, so every candidate judged on that case meets the same judge and
rankings compare like with like. If that judge errors or replies without a
usable verdict, the next judge in rotation order is tried.

When every judge fails, the command stops with exit status `1` rather than
recording a failed case, because a judge outage is a failure of Azathoth, not
of the candidate:

```text
Semantic judging failed with every judge: <judge> raised RuntimeError: down.
```

Judge calls are Azathoth's own cost. They are recorded in each semantic
evaluation's evidence, shown by `run show`, and never charged to a workflow
run, a benchmark total, or a scorecard.

Changing the rotation changes how cases are assigned to judges, so compare
results produced under the same rotation.

# Benchmark Commands

The benchmark command family manages durable benchmark datasets and evaluates
configured workflows against them.

```bash
azathoth benchmark import <FILE>
azathoth benchmark list
azathoth benchmark show <BENCHMARK_ID> [--revision <NUMBER>]
azathoth benchmark history <BENCHMARK_ID> [--limit <COUNT>]
azathoth benchmark export <BENCHMARK_ID> [--revision <NUMBER>]
azathoth benchmark cases <BENCHMARK_ID>
azathoth benchmark case-show <BENCHMARK_ID> <CASE_ID>
```

Benchmarks are revisioned exactly like workflows. Every import appends the
next revision; re-importing an earlier document reverts to its content:

```text
Imported benchmark dataset <BENCHMARK_ID> revision 3 (identical to revision 1).
```

`benchmark show` adds `Revision`, `Imported`, and `Content Digest` lines, and
`benchmark history` lists one line per revision, newest first:

```text
3  2026-10-23T16:02:11+00:00  4f1a9c0e2b7d  1.0.0  5 cases  classify-sentiment  identical to revision 1
```

Runs, comparisons, optimization, `cases`, and `case-show` always use the
latest revision. A changed benchmark is a new revision, never an edit, so a
saved execution's case IDs always mean the cases it judged.

# Add a Case From a Run

Turn one recorded run into a benchmark case with:

```bash
azathoth benchmark add-case <BENCHMARK_ID> \
    --from-run <RUN_ID> \
    --comparison exact|normalized|semantic|schema \
    [--expected '<JSON>'] \
    [--description <TEXT>]
```

The new case replays the run's input: the payload of its
`workflow.input.received` event. Configured runs given `--input`, production
invocations, and benchmark and optimization runs all have one.

A run whose input was resolved, from `--input-file`, `s3://` or a job's
inline content, also gives the case its provenance, the payload of its
`workflow.input.resolved` event, as `input_provenance` (ADR 0117). A run
given a PDF or an image gives the content's handle, which the case's run
reads from the content store by digest, as the run did. The content store
must still hold it.

The expected value is `--expected` when given, and `--expected null` expects
JSON null. Otherwise it is the corrected output of the run's latest bad
feedback that carries one, latest by feedback time with ties going to the
later record. Good feedback never supplies a value, and a later good
judgment does not hide an earlier correction.

The case gets a new ID. Its description defaults to `Added from run
<RUN_ID>.`, and its metadata names the source run and, when feedback supplied
the value, the feedback:

```json
{
  "source_run_id": "<RUN_ID>",
  "source_feedback_id": "<FEEDBACK_ID>"
}
```

The case is appended after every existing case as the benchmark's next
revision. Nothing is edited, the declared version is kept, and earlier
revisions are untouched:

```text
Added benchmark case <CASE_ID> to benchmark dataset <BENCHMARK_ID> revision 2.
```

Any run can become a case of any benchmark. Benchmarks belong to no
workflow, because any workflow can run against any benchmark.

Cases may share an input when they expect different outcomes, because a
judged comparison can accept more than one result for the same input. Each
such case is still judged on its own.

Checks run in this order, and nothing is written when one fails:

```text
unknown benchmark
    Benchmark dataset <BENCHMARK_ID> is not configured.

unknown run
    Run <RUN_ID> was not found.

no workflow input
    Run <RUN_ID> did not receive workflow input.

workflow input received more than once
    Run <RUN_ID> received workflow input more than once.

no --expected and no corrected output
    Run <RUN_ID> has no corrected output; pass --expected.

a schema comparison whose value is not a JSON Schema
    Expected value cannot be used with comparison 'schema': <REASON>

a PDF or image the content store no longer holds
    Run <RUN_ID> received content <DIGEST>, which the content store no longer holds.

an existing case with the same input, comparison, and value
    Benchmark dataset <BENCHMARK_ID> already contains case <CASE_ID> with this input and expected outcome.
```

Values compare as JSON, so `4` and `4.0` are the same value and `true` and
`1` are not. The description plays no part.

A semantic case can be added while no judges are configured, as with
`benchmark import`. Judges are checked when the benchmark is run, compared,
or optimized against.

`benchmark add-case` reads and writes durable state only. It never loads the
runtime and needs no provider credentials.

# Add a Case From a File

A file can become a case without a run first, with `--input-file` in place
of `--from-run` (ADR 0117):

```bash
azathoth benchmark add-case <BENCHMARK_ID> \
    --input-file claim-0412.pdf \
    --comparison exact \
    --expected '{"received": "December 14"}'
```

The file is read as [`workflow run --input-file`](#input-files) reads it:
JSON, text, a PDF or an image, with its media type from its extension
unless `--media-type` gives it, and its content kept in the content store.
The case holds what a run given the file would receive, its handle for a
PDF or an image, and the file's provenance, so the case's run receives it
as that run would.

`--expected` is required, since a file has no feedback. The description
defaults to `Added from <FILE_URI>.`, and the metadata names the file:

```json
{
  "source_uri": "file:///claims/claim-0412.pdf"
}
```

Besides the checks a case from a run shares, a file that cannot be read
fails with the message `workflow run --input-file` gives, and:

```text
no --expected
    A case read from --input-file needs --expected.

--media-type without --input-file
    --media-type requires --input-file.
```

# Cited Cases

A case can hold its run to citing the right segments (ADR 0117). Name each
segment the run must cite with `--require-citation`, as the source a cited
step names and the segment's ID:

```bash
azathoth benchmark add-case <BENCHMARK_ID> \
    --from-run <RUN_ID> \
    --comparison exact \
    --expected '{"received": "December 14", "citations": [{"source": "claim", "segment": "p1.s2"}]}' \
    --require-citation claim:p1.s2
```

A required segment is met by a verified check, of that source and segment,
that a cited step of the case's run kept, read from the content store, not
from the result. By default any check the run kept that did not verify
fails the case too; `--on-unverified ignore` counts only the required
segments. `--on-unverified` alone names an expectation requiring no
segment.

Before an exact, normalized or semantic comparison, every citation and
check in the expected value and the result compares as the segment it
cites, `{"source", "segment"}`, so an expected value names citations by
segment and is met however the model words its quote. A schema comparison
validates the result as it is.

A cited case passes only if its outcome and its citations both pass. Its
score is the outcome's, times the fraction of required segments met and,
unless ignored, the fraction of checks that verified. Its evaluation adds
`citations` evidence, which `run show` prints with the rest:

```text
Evaluator: exact-match 2.0.0
Status: failed
Score: 0.500000 (threshold 1.000000)
Reason: Actual value exactly matched expected value. Citations: 1 of 2 required citations verified; 2 of 3 citations verified. Missing: segment p2.s1 of 'claim'.
Evidence: expected = {"received": "December 14", "citations": [{"source": "claim", "segment": "p1.s2"}]}
Evidence: actual = {"received": "December 14", "citations": [{"source": "claim", "segment": "p1.s2"}]}
Evidence: citations = {"required": 2, "missing": [{"source": "claim", "segment": "p2.s1"}], "checks": 3, "verified": 2, "unverified": 1, "on_unverified": "ignore"}
```

`benchmark case-show` lists a case's input provenance and its required
citations, and `benchmark show` counts its cited cases:

```text
Expected:
  Description: Added from run <RUN_ID>.
  Comparison: exact
  Citations:
    Require: claim p1.s2
    On Unverified: fail
```

A required segment is named once, and a value that is not `SOURCE:SEGMENT`
is refused by the parser:

```text
Citation expectation requires segment p1.s2 of source 'claim' more than once.
```

Benchmark, comparison and optimization runs journal as `workflow run` does
and are given the database's content, so a case's PDF is read by
`segment_pdf` and a cited step is shown the extraction a step of the case's
run kept. A case whose content the store does not hold fails the steps that
read it, and is judged as a failed run; the benchmark goes on.

Execute one configured workflow against a dataset with:

```bash
azathoth benchmark run <BENCHMARK_ID> \
    --workflow <WORKFLOW_ID>
```

Compare several configured workflows against one dataset with:

```bash
azathoth benchmark compare <BENCHMARK_ID> \
    --workflow <WORKFLOW_ID> \
    --workflow <WORKFLOW_ID> \
    --target-latency <SECONDS> \
    --target-cost <USD>
```

Each case judges the workflow's declared result. There is no `--output`
option: which value is the answer belongs to the workflow, not to the command
line.

Every workflow must declare a result. The command fails before loading the
runtime or executing any case when one does not.

A case whose run does not produce the declared result fails the command with
the case named:

```text
Benchmark case <CASE_ID>: Workflow result 'answer' from step <STEP_ID> was not produced.
```

A run that fails without producing its declared result does not abort the
command. The case is recorded with a `workflow-run-failure` evaluation and
counts against accuracy, its comparison's pass count, and, in `compare`, the
candidate's ranking. A run whose steps failed but which still produced its
declared result is judged on that result.

`benchmark run` leads with the ID of its saved execution and reports failed
runs after the per-comparison pass counts:

```text
Execution ID: <EXECUTION_ID>
Benchmark ID: <BENCHMARK_ID>
Workflow ID: <WORKFLOW_ID>
Cases Run: 5
Cases Passed: 4
Accuracy: 0.800000
Passed (exact): 2/2
Passed (normalized): 1/2
Passed (schema): 1/1
Run failures: 1
Total Tokens: 412
Total Latency: 2310 ms
Total Cost: $0.000180
```

`benchmark compare` leads with its saved execution too, then lists every
workflow best first. Under its scorecard, each workflow gets the same
breakdown `run` prints, so a ranking can be explained by which kind of case
each workflow got wrong:

```text
Execution ID: <EXECUTION_ID>
Benchmark ID: <BENCHMARK_ID>

Rank 1
Workflow ID: <WORKFLOW_ID>
Quality: 1.000000
Reliability: 1.000000
Latency: 0.980000
Cost: 0.950000
Overall: 0.982500
Passed (exact): 2/2
Passed (normalized): 2/2
Passed (schema): 1/1
Run failures: 0

Rank 2
Workflow ID: <WORKFLOW_ID>
...
```

The comparison is rendered from the execution record it just saved, so what
is printed is exactly what can be inspected later.

# Saved Benchmark Executions

Every `benchmark run` and `benchmark compare` is saved. There is no opt-in
flag: benchmark evidence costs provider calls, and judge calls, to produce.

```text
benchmark run / benchmark compare
    every case run            persisted, including failed runs
    every case evaluation     persisted, including judge calls
    one execution record      persisted, sharing the printed Execution ID

rejected before any case executes, or judging fails
    nothing persisted
```

A `run` record holds one candidate. A `compare` record holds every compared
candidate with its scorecard, the ranking, and the `--target-latency` and
`--target-cost` that produced it, so a saved ranking can always be explained.
Candidates are identified by workflow ID and candidate signature, not by name.

Each workflow candidate is generated once, before any case executes, and runs
every case, so a record describes exactly one resolved configuration.

List the saved executions of one benchmark with:

```bash
azathoth benchmark executions <BENCHMARK_ID>
azathoth benchmark executions <BENCHMARK_ID> --limit <COUNT>
```

`--limit` must be a positive integer. Executions are listed newest first, one
line each:

```text
<EXECUTION_ID>  2026-10-23T12:32:00+00:00  compare  2 candidates  5 cases  winner <WORKFLOW_ID>  overall 0.982500
<EXECUTION_ID>  2026-10-23T12:31:00+00:00  run  1 candidate  5 cases  workflow <WORKFLOW_ID>  accuracy 0.800000
```

A configured benchmark with no executions prints nothing and exits
successfully. Executions of a benchmark since removed remain listable. An
identifier with neither fails with:

```text
Benchmark dataset <BENCHMARK_ID> is not configured.
```

Inspect one saved execution with:

```bash
azathoth benchmark execution-show <EXECUTION_ID>
```

```text
Execution ID: <EXECUTION_ID>
Recorded: 2026-10-23T12:32:00+00:00
Kind: compare
Benchmark ID: <BENCHMARK_ID>
Benchmark Digest: 4f1a9c0e2b7d
Candidates: 2
Cases: 5
Target Latency: 5.000000 s
Target Cost: $0.001000
Winner Workflow ID: <WORKFLOW_ID>

Rank 1
Candidate ID: <CANDIDATE_ID>
Workflow: classify-sentiment
Workflow ID: <WORKFLOW_ID>
Workflow Revision: 2
Strategy IDs: <STRATEGY_ID>
Passed: 5/5
Accuracy: 1.000000
Passed (exact): 2/2
Passed (normalized): 2/2
Passed (schema): 1/1
Run failures: 0
Quality: 1.000000
Reliability: 1.000000
Latency: 0.980000
Cost: 0.950000
Overall: 0.982500
Rationale: Benchmark aggregate for candidate '<WORKFLOW_ID>' across 5 cases.
Case <CASE_ID>: passed  exact  run <RUN_ID>  evaluation <EVALUATION_ID>
...
```

A `run` execution shows `Kind: run`, no targets or winner, and one block
headed `Candidate` without scorecard lines.

`Benchmark Digest` is the first twelve characters of the content digest of the
exact benchmark revision executed, the same short form `benchmark history`
prints, so an execution matches its revision by eye. `experiment show`
renders the same line. Records written before digests show `unknown`.

An unknown execution fails with:

```text
Benchmark execution <EXECUTION_ID> was not found.
```

Every case line names its run and evaluation, so saved evidence traces
straight to `run show`:

```text
benchmark executions <BENCHMARK_ID>
        │
        ▼
Execution ID ──► benchmark execution-show
                        │
                        ▼
              Case ... run <RUN_ID> ──► run show / run feedback
```

`workflow runs` lists these runs with the `benchmark` source.

`benchmark executions` and `benchmark execution-show` read durable state only.
They do not require provider credentials and never load the runtime.

# Semantic Benchmark Cases

A case with comparison `semantic` is judged by the judge rotation.

Before the runtime loads, `benchmark run` and `benchmark compare` reject a
semantic case while the rotation is empty:

```text
Benchmark case <CASE_ID> uses comparison 'semantic', but no judges are configured.
```

After the runtime loads, and before any case executes, every judge must be
authorized and currently available. A benchmark without semantic cases never
checks the judges, so an unusable judge never blocks deterministic work.

When any case was judged semantically, `benchmark run` reports judging after
the workflow's own totals, kept apart because it is not the workflow's cost:

```text
Passed (semantic): 3/3
Run failures: 0
Total Tokens: 96
Total Latency: 1840 ms
Total Cost: $0.000120
Judge Calls: 3
Judge Cost: $0.000450
```

`Judge Calls` counts every judge call, including fallbacks after a failed or
unusable reply.

`benchmark compare` and `benchmark execution-show` print the same two lines
under every workflow that had semantic cases, after its run failures. Each
workflow's judge calls are its own: a judge's cost is recorded on the case it
judged, never on the run and never in a scorecard.

Benchmarking executes configured workflows.

Like optimization, it produces evidence and does not promote.

# Workflow Input

External input reaches a workflow through one canonical context event,
whichever command supplies it:

```text
benchmark run / benchmark compare / workflow optimize
    each case's input
            │
            ▼
workflow invoke --input
    the caller's JSON
            │
            ▼
workflow run --input
    the operator's JSON
            │
            ▼
workflow.input.received    payload {"input": <value>}
```

A context prompt that binds its variable to `workflow.input.received`, field
`input`, therefore renders the same prompt when its workflow is run,
benchmarked, optimized, or invoked in production. What a workflow is optimized against is
exactly what production feeds it.

Production invocations also keep their own `production.invocation.received`
event, which invocation history reads.

A child, started by a step of another run, records one more event last:
`workflow.lineage.received`, naming its depth, its parent step and its root
run (see [Child Lineage](#child-lineage)). A root records none.

A workflow whose prompt is fixed text, such as
`examples/workflows/simple-prompt.json`, ignores its input.

# Input Files

`workflow run` and `workflow invoke` can read their input from a file
(ADR 0096):

```bash
azathoth workflow run <WORKFLOW_ID> --input-file chapter.md
azathoth workflow invoke <WORKFLOW_ID> --input-file request.json
azathoth workflow run <WORKFLOW_ID> --input-file notes.log --media-type text/plain
```

`--input-file` and `--input` are mutually exclusive. The file becomes a
`file://` reference to its absolute path, with a media type:

```text
.json               application/json   parsed as JSON
.txt                text/plain         decoded into a string
.md, .markdown      text/markdown      decoded into a string
.csv                text/csv           decoded into a string
.pdf                application/pdf    kept, given as a content handle
.png                image/png          kept, given as a content handle
.jpg, .jpeg         image/jpeg         kept, given as a content handle
.webp               image/webp         kept, given as a content handle
```

`--media-type` gives any other file its media type, or overrides the one its
extension implies. It accepts `application/json`, any `text/*` type,
`application/pdf`, `image/jpeg`, `image/png` and `image/webp`, as a
lowercase `type/subtype` with no parameters; any other value is a usage
error. Text content is UTF-8, and a leading byte order mark is dropped.

A PDF or an image is never decoded (ADR 0112). Its content must carry its
media type's signature, and the workflow receives a content handle naming
it instead of its bytes:

```json
{"content": {"digest": "<SHA-256>", "media_type": "application/pdf", "size_bytes": 482113}}
```

The file is resolved before anything else happens:

1. its content is read, up to 10 MiB;
2. it is decoded as its media type, or, for a PDF or an image, checked
   against its media type's signature;
3. its bytes are saved in the configured database's content store, keyed by
   their SHA-256 digest, once however many runs read them;
4. the run, or production invocation, starts.

The workflow receives the decoded value in its `workflow.input.received`
event, exactly as if it had been given with `--input`, so steps and prompts
cannot tell the difference. A `workflow.input.resolved` event follows it, at
the same time and from the same producer, recording where the content came
from:

```json
{"uri": "file:///Users/you/chapter.md", "media_type": "text/markdown", "size_bytes": 18234, "digest": "<SHA-256>"}
```

A run or invocation given `--input` records no such event.

A file that cannot be resolved starts no run and records no invocation. The
command prints why and exits with status 1:

```text
Input file:///Users/you/missing.md does not exist.
Input file:///Users/you/huge.txt is larger than the limit of 10485760 bytes.
Input file:///Users/you/request.json: Content is not valid JSON: Expecting value.
Input file:///Users/you/claim.pdf: Content is not application/pdf: no PDF header in its first 1024 bytes.
Cannot tell the media type of notes.log from its extension; give it with --media-type.
--media-type requires --input-file.
```

The CLI accepts only local files. Other schemes are for other entry points:
the queue worker accepts `s3://` from the locations it allows, and never
`file://` (see [Worker Inputs](#worker-inputs)).

# End-to-End From Checked-In Examples

The sentiment examples exercise every stage from bash:

```text
examples/workflows/classify-sentiment.json     context prompt bound to the workflow input
examples/benchmarks/classify-sentiment.json    five cases: exact 2, normalized 2, schema 1
```

```bash
azathoth workflow import examples/workflows/classify-sentiment.json
azathoth benchmark import examples/benchmarks/classify-sentiment.json

azathoth model authorize <MODEL_IDENTIFIER>

azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f21-000000000000 \
    --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001

azathoth benchmark executions 5e2e0b6a-3c1d-4b7e-9f21-000000000000
azathoth benchmark execution-show <EXECUTION_ID>

azathoth workflow optimize 5e2e0b6a-3c1d-4b7e-9f20-000000000001 \
    --benchmark 5e2e0b6a-3c1d-4b7e-9f21-000000000000 \
    --target-latency 5 \
    --target-cost 0.001

azathoth workflow experiments 5e2e0b6a-3c1d-4b7e-9f20-000000000001
azathoth experiment show <EXPERIMENT_ID>

azathoth workflow promote 5e2e0b6a-3c1d-4b7e-9f20-000000000001 \
    --experiment <EXPERIMENT_ID>

azathoth workflow invoke 5e2e0b6a-3c1d-4b7e-9f20-000000000001 \
    --input '"The checkout flow was painless."' \
    --output text
```

With `--output text`, the invocation prints the declared result as the
production emission:

```text
Invocation ID: <INVOCATION_ID>
Status: succeeded
Result:
{
  "result": "positive"
}
```

The exact cases demand the bare lowercase label. The normalized cases accept
any letter case and surrounding whitespace. The schema case accepts either
label for neutral text, so it checks the answer's form rather than its
judgment.

`examples/benchmarks/classify-sentiment-semantic.json` judges the same
workflow by meaning. Its three semantic cases need at least one authorized
judge:

```bash
azathoth model authorize <JUDGE_MODEL_IDENTIFIER>
azathoth judge add <JUDGE_MODEL_IDENTIFIER>

azathoth benchmark import examples/benchmarks/classify-sentiment-semantic.json

azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f22-000000000000 \
    --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

## Capturing a Corrected Run as a Case

The word-count examples need no provider models:

```text
examples/tools/word-count.json, word-count-process.json
examples/workflows/word-count-messages.json    result 'count'
examples/benchmarks/word-count.json            one exact case
```

```bash
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/word-count-messages.json
azathoth benchmark import examples/benchmarks/word-count.json

azathoth workflow run a1000000-0000-4000-8000-000000000002 \
    --input '"the old ones wait — and dream"' \
    --output result
```

The tools count whitespace-delimited words, so the dash counts and the run
prints `7`. Record what it should have said, then capture the run:

```bash
azathoth workflow runs a1000000-0000-4000-8000-000000000002

azathoth run feedback <RUN_ID> \
    --bad \
    --reason "A dash is not a word." \
    --corrected-output 6

azathoth benchmark add-case b1000000-0000-4000-8000-000000000001 \
    --from-run <RUN_ID> \
    --comparison exact \
    --description "Dashes are not words."

azathoth benchmark history b1000000-0000-4000-8000-000000000001

azathoth benchmark run b1000000-0000-4000-8000-000000000001 \
    --workflow a1000000-0000-4000-8000-000000000002
```

Revision 2 holds both cases, and the run now reports `Cases Run: 2` and
`Cases Passed: 1`: the miscount is a regression case every later candidate is
judged against.

# CLI JSON Arguments

The CLI parser accepts JSON-compatible command-line values for:

```text
workflow run --input
workflow invoke --input
run feedback --corrected-output
benchmark add-case --expected
```

Values are parsed using JSON rather than treated as raw strings.

Therefore:

```bash
--input '"hello"'
```

represents the JSON string:

```text
hello
```

while:

```bash
--input '{"request":"hello"}'
```

represents a structured object.

Invalid JSON is rejected at the command boundary.

Benchmark documents are not command-line arguments: whole benchmarks live in
the document passed to `benchmark import`. `benchmark add-case --expected`
supplies the expected value of one case built from a recorded run.

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

WorkflowProductionState

WorkflowProductionRevision / WorkflowProductionRevision summaries

ProductionInvocation / ProductionInvocation summaries

ProductionInvocationResult

WorkflowBenchmarkResult / WorkflowBenchmarkRanking

WorkflowBenchmarkExecutionRecord / WorkflowBenchmarkExecutionRecord summaries

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

execute_configured_benchmark

compare_configured_benchmarks

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

initial context

StrategyExecutor / WorkflowRunner path
```

into a `WorkflowRun`.

`configured_run_context(workflow_input)` builds the initial context: one
workflow input event produced by `CONFIGURED_RUN_PRODUCER`
(`azathoth.configured`) when a `WorkflowRunInput` is given, and an empty
context otherwise.

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

# Benchmark Application Services

`execute_configured_benchmark` and `compare_configured_benchmarks` compose:

```text
runtime

workflow identity, or identities

benchmark dataset

workflow scoring policy (compare only)

evidence recorder
```

into a `WorkflowBenchmarkResult` or a `WorkflowBenchmarkRanking`, whose `id`
is the ID of the execution record saved for it.

The installed CLI always supplies a SQLite-backed
`WorkflowBenchmarkEvidenceRecorder`, so every case run, every evaluation, and
one execution record are persisted. Without a recorder, the services keep no
evidence beyond their returned result.

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
        ├── with --experiment: experiment repository
        │       └── rebuild_workflow_candidate(winner signature)
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

`workflow production` shows current state; `workflow revisions` shows audit
history.

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
                         │
                         ▼
 workflow production / workflow revisions
 workflow invocations / invocation show
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

production inspection
    ≠
production change

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
