# Changelog

Each release of Azathoth, newest first. Every change of substance was made by
an [architecture decision](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/README.md), linked from its entry. The
release dates are on the
[GitHub releases](https://github.com/EldritchInc/azathoth/releases) and on
[PyPI](https://pypi.org/project/azathoth-ai/#history).

## Unreleased

### Documents In

- **A workflow's input can be a PDF or an image.** `application/pdf`,
  `image/png`, `image/jpeg` and `image/webp` join JSON and `text/*`, by
  reference from the CLI or a worker. The content is checked against its
  media type's signature, kept in the content store, and given to the
  workflow as a content handle naming its digest, media type and size
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).
- **A job's inline input can hold a document as base64, and name its
  origin.** Any inline input may name where its content durably lives, such
  as an S3 object with its version ID and ETag; the origin is recorded with
  the input's digest in the run's `workflow.input.resolved` event. A request
  that names no origin digests exactly as before
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).
- **An `s3://` input records the object version it was read from.** A
  worker records the `VersionId` and `ETag` of the response that held the
  bytes as the input's origin, so evidence names the exact object even after
  the key is overwritten
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).
- **`invocation show` prints an input's provenance.** Its URI or inline
  origin, version, media type, size and digest follow the input under
  `Input Provenance`. A run given a PDF or image cannot become a benchmark
  case yet, and `benchmark add-case --from-run` says so
  ([ADR 0112](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0112-accept-binary-inputs.md)).

## 1.2.0

Azathoth 1.2 serves workflows to AI clients. `azathoth-mcp`, a new package
released with Azathoth at the same version, offers the promoted workflows an
operator lists as Model Context Protocol tools, to Claude Desktop, IDEs and
agents, locally over stdio or to a team over HTTP behind the organization's
identity provider. Everything 1.1 promised is unchanged: documents, commands,
documented output and the database schema are as they were.

The AWS stack, the worker and the S3 tools are unchanged, and the image only
gained `azathoth-mcp`, which the stack does not run, so this release was not
deployed to the AWS sandbox again
([Release Validation](https://github.com/EldritchInc/azathoth/blob/main/docs/release-validation.md#9-the-aws-deployment)).

### Serving Workflows to AI Clients

- **`azathoth-mcp` serves promoted workflows as MCP tools.** It is a separate
  distribution, released with Azathoth at the same version and requiring its
  minor release. Only the workflows an operator lists in an exposure document
  are offered, each as one tool, under the name and description written for
  it; nothing that changes a workflow is ever offered ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **Every call is a recorded, idempotent invocation** of the workflow's
  active production revision, run as `job run` runs a job request: a repeated
  key replays, an interrupted invocation resumes, and the caller is recorded
  with it. `get_invocation` returns an invocation's input, outcome, caller and
  run, step by step ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **Over HTTP it is an OAuth 2.1 resource server.** It accepts only signed
  tokens from the organization's identity provider, issued for its own URL,
  and grants each tool by its own scope; it advertises them in its Protected
  Resource Metadata, and never logs a token. Without authorization it listens
  only on a loopback address ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).
- **It ships in the container image**, and the release publishes both
  packages together. [Serving Workflows Over MCP](https://github.com/EldritchInc/azathoth/blob/main/docs/mcp.md) covers Claude Desktop, teams and the container
  ([ADR 0111](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0111-serve-promoted-workflows-over-mcp.md)).

### Upgrading From 1.1

Nothing changes for an existing installation. Upgrade, and run `azathoth init`
as after every upgrade:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

To serve workflows over MCP, install `azathoth-mcp` into the same venv. From
then on, upgrade both in one command: each release of it requires its own
minor release of `azathoth-ai`.

## 1.1.0

Azathoth 1.1 runs in production. Programs send it jobs through a queue,
workers on AWS run them against one PostgreSQL database, and a run cut short
by a deploy or a lost machine resumes where it stopped. Workflows compose from
a standard tool library that ships in the package, map a child over a list,
take their inputs by reference, and process data of any size from S3. Models
run on OpenRouter or Amazon Bedrock, and every run can be traced.

### Composing Workflows

- **A standard tool library ships in the package**, installed by
  `azathoth init` ([ADR 0095](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0095-ship-a-standard-tool-library.md)).
  Composing workflows needs no checkout of the repository.
- **Data-shaping tools** pick, build, merge and validate JSON and split, join
  and fill in text: `json_select`, `json_object`, `json_merge`,
  `validate_json`, `chunk_text`, `join_text` and `render_template`.
- **A step input may be a constant**, written in the workflow document
  ([ADR 0094](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0094-constant-step-inputs.md)).
- **Loops are budgeted from their settings**: `loop_workflow` 1.1.0 takes a
  `budget_seconds`, and every process tool is told its own timeout
  ([ADR 0093](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0093-budget-loops-from-their-settings.md)).
- **`map_workflow` runs a child once per item of a list**, several at a
  time, and returns the results in order
  ([ADR 0106](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0106-map-a-child-workflow-over-a-list.md)).
- **A child records where it came from**: the step and run that started it,
  and its root, with nesting bounded by the engine
  ([ADR 0104](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0104-record-lineage-in-a-childs-initial-context.md)).

### Inputs and Jobs

- **An input is a value or a reference**, a `file://` or `s3://` URI with a
  media type, resolved before the run starts and kept by its digest
  ([ADR 0096](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0096-accept-inputs-as-values-or-references.md),
  [ADR 0108](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0108-read-inputs-from-s3.md)).
- **A versioned job envelope** requests an invocation and reports its result,
  with an idempotency key that makes a repeated request replay
  (`azathoth job run`,
  [ADR 0097](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0097-carry-invocations-in-a-versioned-job-envelope.md)).
- **Data larger than an input may be** stays in S3: `split_s3_object` streams
  an object into chunk objects, and `read_s3_object` reads one back
  ([ADR 0110](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0110-split-and-read-s3-objects.md)).

### Running in Production

- **PostgreSQL** keeps durable state for many processes at once, selected by
  a `postgresql://` `AZATHOTH_DATABASE`
  ([ADR 0102](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0102-keep-durable-state-in-postgresql.md)).
- **Interrupted runs resume from their journal**, under a lease one process
  holds at a time (`azathoth run resume`,
  [ADR 0105](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0105-resume-interrupted-runs-from-a-journal.md)).
- **A container image** for amd64 and arm64, with an SBOM and provenance,
  signed by the release workflow
  ([ADR 0101](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0101-ship-azathoth-as-a-container-image.md)).
- **Queue workers** take job requests from SQS, settle each message by its
  result, keep a running job's message hidden, and drain on SIGTERM
  (`azathoth worker run`,
  [ADR 0107](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0107-run-jobs-from-a-queue.md)).
- **One CloudFormation template deploys a fleet** of workers on Fargate, with
  least-privilege IAM, secrets from Secrets Manager and scaling on the queue
  ([ADR 0109](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0109-deploy-on-aws.md)).

### Models and Evidence

- **Amazon Bedrock** runs models beside OpenRouter, with its own discovery,
  IAM policy and prices
  ([ADR 0103](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0103-run-models-on-amazon-bedrock.md)).
- **OpenTelemetry tracing** of every run, step and model call, as an optional
  extra ([ADR 0100](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0100-trace-workflows-with-opentelemetry.md)).
- **A step can report its confidence**, recorded with its outputs
  ([ADR 0098](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0098-record-step-confidence.md)).
- **The optimizer evaluates its final generation**, so a candidate proposed
  last is measured before the winner is chosen
  ([ADR 0091](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0091-evaluate-the-final-generations-proposals.md)),
  and **`workflow promote --experiment` deploys an experiment's winner**
  directly ([ADR 0092](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0092-promote-an-optimization-experiments-winner.md)).

### Security

- **Process tools see only the environment they declare**, beside a small
  base set, so a tool never receives a key it did not ask for
  ([ADR 0099](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0099-give-process-tools-only-the-environment-they-declare.md)).

### Upgrading From 1.0

Upgrade the package, then run `init` once against each database:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

1.1 upgrades a 1.0 database in place the first time it opens it, adding the
tables that record a run as it executes. `init`, which is new in 1.1, then
installs the standard tools, which ship in the package from 1.1 on. A
database holding the composition tools 1.0 shipped as examples gets:

```text
Database: /path/to/azathoth.db (existing)
Installed tool run_workflow@1.0.0 revision 2.
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
```

Two changes can stop a workflow that ran on 1.0:

- Process tools no longer inherit Azathoth's environment. The standard tools
  grant themselves what they need; a process tool of your own that relied
  on an inherited variable, such as a provider key, must grant it (see
  [Process Environment](https://github.com/EldritchInc/azathoth/blob/main/src/azathoth/tools/README.md#process-environment)).
- A workflow that requires `loop_workflow` 1.0.0, the example 1.0 shipped,
  must name 1.1.0. The 1.0.0 implementation grants itself nothing, so its
  children no longer see `AZATHOTH_DATABASE`, and open `azathoth.db` in
  whatever directory they run in instead of yours. `run_workflow` 1.0.0
  needs no change: `init` gives it its grants as its next revision.

## 1.0.0

The first release: workflows composed from prompt, tool and child-workflow
steps, run and recorded as evidence; benchmarks with exact, normalized,
schema and model-judged cases; an optimizer that searches for cheaper
authorized models; and deliberate promotion to production. Models ran on
OpenRouter, and state was kept in SQLite. Its decisions are ADR 0001 to
ADR 0090.
