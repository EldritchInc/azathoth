# Changelog

Each release of Azathoth, newest first. Every change of substance was made by
an [architecture decision](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/README.md), linked from its entry. The
release dates are on the
[GitHub releases](https://github.com/EldritchInc/azathoth/releases) and on
[PyPI](https://pypi.org/project/azathoth-ai/#history).

## Unreleased

- `azathoth.api`, a public service API that the command line, azathoth-mcp
  and the coming local editor all call. It browses and imports workflows,
  tools and benchmarks, lists the models providers serve, keeps the model
  portfolio, initializes databases, and runs and invokes workflows,
  reporting each step and context change to a callback as it happens and
  stopping when cancelled. It returns its own
  frozen models, each with its equivalent `azathoth` command, raises errors
  with stable codes, and is provisional until 1.4.0
  ([ADR 0120](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0120-public-service-api.md)).
- azathoth-mcp runs each tool call through the service API. A call now asks
  the providers what they serve, as `azathoth job run` does, rather than
  once while production stays the same, so a model authorized or a tool
  imported reaches a running server at once; a call the client cancels
  cancels its invocation, which the same call under its key resumes
  ([ADR 0120](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0120-public-service-api.md)).
- `azathoth.api` runs and invokes a workflow on a file: `RunFile` holds a
  document or an image, JSON or text, checked and kept as `--input-file`
  keeps one, and refused before anything runs when it is not its media type
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).
- `azathoth.api` checks a workflow document without saving it, naming every
  problem with where it is and its step; says, step by step, whether a
  document could run here now and on which models; and lists the
  portfolio's models that meet a step's requirements, by the rules a run
  uses
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).
- `azathoth.api` reads back the runs an instance kept: a workflow's runs
  newest first, and one run with its input, its result, and each step's
  output, values, measurements and failed attempts
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).
- `azathoth.api` tries one step of a workflow document alone, on the inputs
  given, a file among them, reporting its events as a run does and keeping
  no run
  ([ADR 0121](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0121-service-api-second-round.md)).
- Every workflow, tool and benchmark revision records its lineage: a
  revision digest that covers its content and every revision before it, the
  revision it was built on, and who imported it. Every portfolio entry
  records its digest, who authorized it and when. The database schema is now
  version 3; run `azathoth init` once to upgrade a PostgreSQL database, which
  records the lineage it already holds. An SQLite file is upgraded when it is
  opened
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- Importing a document identical to the latest revision appends nothing and
  says so: `Workflow <WORKFLOW_ID> is unchanged at revision <NUMBER>.`, and
  likewise for tools and benchmarks. Before, it appended a duplicate
  revision. Importing an earlier revision's document still appends a revert
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- Who imports is `AZATHOTH_AUTHOR`, as `Name <email>` or `Name`, or else the
  operating system's username; a malformed `AZATHOTH_AUTHOR` stops the
  import, authorizing a model, and adding a benchmark case. The standard
  tools are recorded as Azathoth's
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- `workflow show` and `benchmark show` name each revision's digest, parent
  and author, and history lines end with who imported each revision when
  that is known
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- `azathoth.api` reports each revision's revision digest, parent and author,
  and each portfolio entry's digest, author and time. Imports take
  `based_on`, building on an earlier revision to fork, and return
  `WorkflowImport`, `ToolImport` and `BenchmarkImport`, which say whether a
  revision was created; `api.open` takes the `author` to record
  ([ADR 0122](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0122-lineage-and-digests.md)).
- Sensitivity labels: a run's input, a job's input and a benchmark case may
  be labelled `public`, `internal` or `restricted`, with `--sensitivity`,
  an input source's `sensitivity` or the service API's `sensitivity=`.
  Unlabelled data is internal and unchanged. A child workflow and a case
  made from a run are never less sensitive than their source, and a
  benchmark is as sensitive as its most sensitive case
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- Each portfolio model declares what its provider does with data:
  `model authorize --no-retention --no-training`, or `model policy` at any
  time, which also shows who declared it and when. The database schema is
  now version 4; run `azathoth init` once to upgrade a PostgreSQL database
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- Restricted input reaches only models declared to neither retain nor train
  on data. A context prompt step that would send it anywhere else sends
  nothing and says which model and what to declare, and a production
  invocation's caller is told the same. Steps that choose a model, and
  production with approved substitutes, choose a private one first;
  semantic judges and the optimizer's substitutes of restricted cases must
  be private; readiness and model matching take a label
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- azathoth-mcp: an exposure document's tool may take `"sensitivity":
  "restricted"`, the operator's declaration that its client may hold
  restricted data. Its calls are restricted, and `get_invocation` returns no
  restricted invocation through a tool not so exposed
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- Labels are shown wherever data is: the API's run, invocation and
  benchmark views, a `Sensitivity:` line in show commands for data that is
  not internal, a warning on standard error from every command that prints
  restricted data, and the `azathoth.sensitivity` span attribute. Tools are
  not gated by labels in 1.4
  ([ADR 0123](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0123-sensitivity-labels.md)).
- A remote: `azathoth remote serve` serves an instance's workflows, tools
  and benchmarks over HTTP, for other instances to push to and pull from,
  with the new `remote` extra. `azathoth remote push` and `pull`, and the
  service API's `instance.remote(url)`, send each document's latest
  revision, the revisions it was reached by, and the tool versions, child
  workflows and benchmark content it needs, sending only what the other
  side lacks. Production state, the portfolio and runs never travel
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- Revision digests are a revision's identity everywhere; each instance
  numbers what it saves. A remote moves only forward: a push whose lineage
  diverged there is refused, and a pull forks a lineage that diverged here
  on the revision its pulled revisions build on, so nothing is lost
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- A remote's owner issues bearer tokens with `azathoth remote token create`,
  shown once and kept only as digests; `list` and `revoke` manage them, and
  a client reads its token from `AZATHOTH_REMOTE_TOKEN`. The database schema
  is now version 5; run `azathoth init` once to upgrade a PostgreSQL
  database
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- A remote refuses restricted data unless it is served with
  `--accept-restricted`, and a pull brings restricted benchmarks only with
  `--include-restricted`
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- A remote's authentication, policy and audit are seams a plugin fills,
  through the `azathoth.remote` entry-point group; the core's let only the
  owner in and audit nothing. A remote's capabilities name its protocol,
  versions, edition and plugins, and a client refuses another protocol
  before sending anything
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).
- `azathoth.api`'s `models.matching(..., scope="catalog")` matches every
  model the providers serve, marked authorized or not, for a pulled
  workflow's steps. The container image includes the `remote` extra
  ([ADR 0124](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0124-remote.md)).

## 1.3.0

Azathoth 1.3 reads documents and keeps the evidence of where each answer
came from. A workflow can be given a PDF or an image; a prompt step can show
it to a model or cite the passages of it the answer rests on, and every
citation is checked against the text before it is kept. Citations are
scored in benchmarks and optimization, and export as W3C Web Annotations
that link back into the documents, S3 objects among them. A workflow can
declare the schemas of its input and its result, and every production
invocation is held to them; and a step can call a tool another MCP server
serves, pinned to that tool's schemas. Documents, commands, the output of
every command that succeeds, and the database schema are as 1.2 left them.

This release changes what the image runs on AWS: the worker records the
version of every S3 object it reads, and the image now reads PDFs. Release
validation requires such a release to be deployed to an AWS sandbox before
it ships, and no sandbox was available, so this release was not deployed.
The template was read, the worker run against botocore's `Stubber` and the
S3 tools against a stand-in for S3, as for every release; what only a real
deployment proves, that the stack still runs the changed worker and image
on real SQS and S3, is unproven for 1.3.0
([Release Validation](https://github.com/EldritchInc/azathoth/blob/main/docs/release-validation.md#9-the-aws-deployment)).

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
- **A tool can read a document its run received.** A process
  implementation's `content_inputs` are given as files of the content their
  handles name, written and removed by the engine, so a tool needs no access
  to the content store. A handle naming content the run, or a run above it,
  never received is refused before the tool runs
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md)).
- **A document tool's extraction is checked, kept and recorded by the
  engine.** An implementation's `extraction_output` must be a segmented
  text of content the tool was given. The engine keeps it in the content
  store, records it as a resource of the step, and outputs an extraction
  handle in its place
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md)).
- **The standard `segment_pdf` tool divides a PDF into citable segments.**
  Each text box is a segment, `p<PAGE>.s<N>`, with its page and its box in
  points from the crop box's top-left corner, and every page is listed with
  its size and whether it has text. It refuses a PDF of more than
  `max_pages`, 300 by default, or one that needs a password. It reads PDFs
  with pdfminer.six, which the new `documents` extra installs, and the
  container image includes
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md)).
- **A model step can be shown the documents and images its run received.**
  A template variable bound to a content handle shows the model that content
  where the variable stands, beside the template's text, as a prompt of
  parts. The engine reads the bytes from the content store as the prompt is
  sent, only for content the run, or a run above it, received, and no event
  or run holds them. A prompt of text is unchanged
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **OpenRouter models are shown images and PDFs in OpenRouter's own
  parts.** An image is sent as an `image_url` and a PDF as a `file`, in the
  prompt's order, and a PDF is read by the model itself: the request pins
  OpenRouter's PDF engine to `native`, so no paid OCR service reads it in
  the model's place
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **Bedrock models are shown images and PDFs as Converse blocks.** An image
  is an `image` block and a PDF a `document` block named neutrally, in the
  prompt's order. Converse's limits, 20 images of 3.75 MB and 5 documents of
  4.5 MB, with text beside any document, are checked before anything is
  sent. Bedrock does not say which models read documents, so the pricing
  document may add `file` to a model's input modalities under
  `input_modalities`
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **A model is shown only what its catalog says it reads.** A step that
  shows content declares `image` or `file` among its required input
  modalities, and portfolio selection chooses only models that take them.
  Whatever model a step is bound to, its rendered prompt is checked against
  the model's catalog entry before the model is called
  ([ADR 0115](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0115-multimodal-prompts.md)).
- **An example PDF to try it on.** `examples/documents` holds a two-page
  claim, written by a script byte for byte, a workflow that divides it with
  `segment_pdf` into the segments a model can cite, and one that answers
  from it, citing it. The new
  [Reading Documents and Citing Them](https://github.com/EldritchInc/azathoth/blob/main/docs/documents.md)
  guide walks through both and exports the citations
  ([ADR 0114](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0114-read-documents-with-tools.md);
  [ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).

### Evidence Out

- **Source anchors say where in exactly which content something is.**
  `azathoth.citations` writes a place in content as W3C Web Annotation
  selectors, under their own names: a quote with its context, a span in
  Unicode code points, and a PDF page or image region. An anchor names the
  content's digest and origin, and the extraction whose text its selectors
  count
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **An extraction is the text a tool took from a source, and its
  segments.** Each segment has an ID a model can cite, its span of the text,
  and, on a PDF, its page and bounding box. The whole output is stored as
  canonical JSON, so its digest names it, and an anchor can be checked again
  from the content store alone
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **A citation is checked against the segment it names, with no model
  involved.** A quote found exactly is `verified`; one found only after
  normalizing whitespace, quotes and dashes is `verified_normalized`; and
  otherwise the check says `quote_not_found` or `unknown_segment`. A found
  quote is anchored by the source's own text, its position, and on a PDF its
  page and box
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **Text can be segmented and cited with no document tool.**
  `segment_text` makes one segment per paragraph, deterministically, under
  a version of its own that changes only when its output does
  ([ADR 0113](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0113-anchor-and-verify-citations.md)).
- **A model step is shown an extraction's segments by the IDs it may
  cite.** A template variable bound to an extraction handle renders its
  segments as `[p1.s2] text` inside a `source` named by the variable. Only
  an extraction a step of the run, or of a run above it, kept is shown
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).
- **A cited step's citations are checked before anything relies on them.**
  A JSON prompt step naming a `citations` policy has every
  `{"source", "segment", "quote"}` in its reply checked against the
  extraction it names and replaced by its check, with an anchor naming the
  source's origin. A citation not verified fails the attempt, so the step
  asks again, unless the policy keeps it, and every check is kept in the
  content store and recorded as the step's `citations` resource
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).
- **A Bedrock model's own citations of a PDF are checked the same way.** A
  text prompt step whose policy is `{"native": true}` has Bedrock cite the
  PDFs it shows; each citation is checked against the segments, on the pages
  it names, of the extraction the step also shows, and the step outputs its
  text with the checks, kept and recorded as any cited step's
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).
- **`invocation show` prints every check a cited step kept.** After the
  result, each cited step of the invocation's run names its record and
  lists its checks, one line each: the status, the source, the segment and
  the quote. A record is read back with `stored_citation_checks`, and each
  check can be verified again from the content store alone
  ([ADR 0116](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0116-cited-prompt-steps.md)).

### Evidence in Benchmarks

- **A benchmark case can hold a document.** A case names its input's
  provenance, as a run records it, and a case given a PDF or an image holds
  its handle, with the content kept in the content store by digest.
  `benchmark add-case --from-run` takes a run given a document, and
  `benchmark add-case --input-file` makes a case straight from a file
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **Benchmark, comparison and optimization runs read documents.** Every case
  runs with the database's journal and content, as `workflow run` does, so
  `segment_pdf` reads a case's PDF and a cited step keeps its checks. A case
  whose content the store no longer holds is judged as a failed run
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **A case can require its run to cite the right segments.** An expected
  outcome names the segments its run must cite and whether an unverified
  citation fails it; `benchmark add-case --require-citation claim:p1.s2`
  and `--on-unverified` name them. Each is judged from the checks the run's
  cited steps kept, never from the result, and the case's evaluation
  records how many were met
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **Cited runs are scored on their citations.** A scorecard gains a
  citation score, the fraction of a run's checked citations that verified,
  and a cited run's overall score is the mean of five dimensions, so
  comparisons, experiments and optimization prefer candidates whose
  citations verify. Runs with no cited step score as they always did
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **What a run cited exports as W3C Web Annotations.** `azathoth run
  annotations <RUN_ID>` and `azathoth invocation annotations
  <INVOCATION_ID>` print every verified check as an annotation highlighting
  its anchor's place, in exactly the document version it came from, ready
  for a reviewer's annotation tools; the same checks always export to the
  same bytes
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **A citation links to its page.** `azathoth invocation show --links`
  follows each verified citation with a link to its document at its page:
  the origin for `https` and `file` documents, and a presigned GET of the
  exact object version for `s3://` ones, valid for
  `AZATHOTH_LINK_EXPIRY_SECONDS`, an hour by default
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **Results that cite compare by what they cite.** Before an exact,
  normalized or semantic comparison, every citation and check compares as
  `{source, segment}`, so an expected answer names its citations by segment
  however the model words its quote
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).

### Workflow Contracts

- **A workflow declares the JSON Schemas of its input and its result.**
  `input_schema` describes what the workflow receives, a document as its
  content handle, and `output_schema` its declared result. Both travel into
  production with the promoted workflow, and `workflow show` and `workflow
  production` print them; a workflow without them reads and digests as
  before
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).
- **Every production invocation is checked against its workflow's
  contract.** `workflow invoke`, jobs, workers, MCP calls and child
  workflows share one check against the promoted schemas: an input that
  breaks the input schema fails with `invalid_input` before any run starts,
  and a result that breaks the output schema fails with the new
  `invalid_output`, its run kept. Each names every violation by its JSON
  path, and lists them in its metadata
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).
- **`workflow import` says why a document is refused** when the workflow
  states a reason, such as a schema that is not a JSON Schema
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).
- **MCP tools take their workflow's schemas.** A workflow exposed without
  an operator's `input_schema` takes the promoted workflow's input schema,
  and every workflow tool names an `outputSchema`, the outcome it returns,
  its `result` held to the workflow's output schema
  ([ADR 0118](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0118-workflow-input-and-output-schemas.md)).

### Calling MCP Tools

- **A tool implementation can bind a tool an MCP server serves.** An `mcp`
  implementation names its server, by the command of a stdio server or the
  URL of an HTTP one, the remote tool, the digest of that tool's schemas
  when it was pinned, and the variable holding an HTTP server's bearer
  token; it runs no source. `tool implementation show` prints the binding,
  and every other implementation reads and digests as before
  ([ADR 0119](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0119-call-mcp-served-tools.md)).
- **A tool step calls the MCP tool it is bound to.** Each call connects
  anew, over stdio or streamable HTTP, and calls the tool only while its
  schemas match the pin; its output is the tool's structured content, or
  its text. A stdio server gets only the variables its implementation
  grants, and an HTTP server the bearer token its authorization variable
  holds, with the step's trace context. Install `azathoth-ai[mcp]` to call
  MCP tools
  ([ADR 0119](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0119-call-mcp-served-tools.md)).
- **`azathoth tool from-mcp` writes an MCP tool's document.** It lists a
  server's tools and prints the named tool's document, its definition
  taking the tool's name, description and schemas and its implementation
  pinned to them, ready for `tool import`; writing it again for a tool
  whose schemas changed shows a new implementation
  ([ADR 0119](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0119-call-mcp-served-tools.md)).
  The new [Calling MCP Tools](https://github.com/EldritchInc/azathoth/blob/main/docs/mcp-tools.md)
  guide walks through one, with an example server in `examples/mcp`.

### Fixes

- **Workflows with tool steps can be compared and optimized.** A tool step
  stated no cost, so a run with one could not be scored; it now states
  that its own work costs nothing, and a step that starts child runs, such
  as `run_workflow`, costs what its children did, read from their journals
  ([ADR 0117](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0117-citations-as-evidence.md)).
- **A command stopped as a process tool starts no longer hangs.** A tool
  cancelled before it was given its inputs is killed, its stdin closed, and
  only then waited for. On a Python without CPython's gh-119710 fix, waiting
  for it with its stdin still open never returned, so a run stopped by
  SIGTERM could keep its lease and never exit.

### Upgrading From 1.2

Nothing changes for an existing installation. Upgrade, and run `azathoth init`
as after every upgrade; it installs `segment_pdf`, the one new standard tool:

```bash
python -m pip install --upgrade azathoth-ai
azathoth init
```

```powershell
python -m pip install --upgrade azathoth-ai
azathoth init
```

If you serve workflows with `azathoth-mcp`, upgrade it in the same command,
as [Installing Azathoth](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md#upgrading-leaving-and-uninstalling) shows: 1.3 of it requires 1.3 of
`azathoth-ai`.

Reading PDFs and calling MCP tools each need an extra, installed only by
those who use them: `azathoth-ai[documents]` and `azathoth-ai[mcp]`.
`azathoth-mcp` brings the MCP SDK with it.

Three refusals the 1.2 documentation quoted now read differently, for anyone
who matches on their text:

- a tool implementation that is not a process one and declares a command,
  or a timeout, is refused with `Only process tool implementations may
  declare a command.` or `Only process and MCP tool implementations may
  declare a timeout.`, where one message named both;
- the refusal of an unsupported runtime lists `mcp, process, python`;
- `workflow import` adds the reason a document is not a valid workflow, when
  the workflow states one, after `Workflow document is not a valid
  WorkflowSpecification.`

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
Installed tool segment_pdf@1.0.0 revision 1.
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
