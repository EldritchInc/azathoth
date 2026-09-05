# Getting Started

This guide walks through Azathoth's OSS V1 lifecycle from a fresh development
checkout to an active production workflow.

By the end, you will have:

```text
installed Azathoth
      │
      ▼
imported a workflow
      │
      ▼
inspected provider models
      │
      ▼
authorized models
      │
      ▼
executed configured behavior
      │
      ▼
run empirical optimization
      │
      ▼
promoted the workflow
      │
      ▼
invoked active production
```

The guide uses the canonical checked-in workflow:

```text
examples/workflows/simple-prompt.json
```

That file is not pseudocode.

The test suite verifies that it exactly matches Azathoth's canonical
`WorkflowSpecification` serialization.

## 1. Create a Development Environment

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Confirm the installed application is available:

```bash
azathoth --version
```

and inspect the command surface:

```bash
azathoth --help
```

The installed application also supports:

```bash
python -m azathoth.cli
```

## 2. Use an Isolated Database

Azathoth's CLI stores durable application state in SQLite.

For this walkthrough, create an isolated temporary directory:

```bash
export AZATHOTH_QUICKSTART_DIR="$(mktemp -d)"
export AZATHOTH_DATABASE="$AZATHOTH_QUICKSTART_DIR/azathoth.db"
```

Confirm the value:

```bash
printf '%s\n' "$AZATHOTH_DATABASE"
```

This keeps the walkthrough separate from any existing Azathoth configuration.

The CLI uses:

```text
AZATHOTH_DATABASE
```

to select durable application storage.

If the variable is not set, Azathoth uses:

```text
azathoth.db
```

in the current working directory.

## 3. Import the Canonical Workflow

Import the checked-in example:

```bash
azathoth workflow import \
    examples/workflows/simple-prompt.json
```

The expected confirmation is:

```text
Imported workflow 11111111-1111-1111-1111-111111111111.
```

At this point:

```text
JSON document
      │
      ▼
domain validation
      │
      ▼
WorkflowSpecification
      │
      ▼
SQLite
```

No workflow has executed.

No model has been selected.

Nothing has been promoted to production.

Import is a durable configuration operation.

## 4. Inspect the Workflow

List configured workflows:

```bash
azathoth workflow list
```

The canonical example appears as:

```text
11111111-1111-1111-1111-111111111111  1.0.0  simple prompt
```

Inspect it:

```bash
azathoth workflow show \
    11111111-1111-1111-1111-111111111111
```

The example contains one prompt-backed step.

Its durable intent is approximately:

```text
Workflow
    simple prompt
        │
        ▼
Prompt Strategy
    answer request
        │
        ▼
Prompt
    "Answer the request concisely."
        │
        ▼
PortfolioModelSelection
```

The example uses default text model requirements.

It does not hard-code one provider model.

Import, list, and show require no provider credentials.

That is deliberate:

```text
durable workflow inspection
        ≠
runtime model execution
```

## 5. Configure OpenRouter

Prompt-backed execution requires current provider state and executable model
implementations.

Azathoth OSS V1 provides OpenRouter integration.

Export an OpenRouter API key into the current shell:

```bash
export OPENROUTER_API_KEY='YOUR_OPENROUTER_API_KEY'
```

The key is process-local runtime configuration.

It is not persisted inside the workflow.

```text
WorkflowSpecification
    durable intent

OPENROUTER_API_KEY
    process-local provider credential
```

Do not place the key in the workflow JSON document.

## 6. Inspect Current Provider Models

With OpenRouter configured:

```bash
azathoth model list
```

Azathoth synchronizes current provider model state and renders entries as:

```text
MODEL_IDENTIFIER  DISPLAY_NAME
```

Model identifiers are provider-qualified.

For OpenRouter they have the form:

```text
openrouter/<PROVIDER_NATIVE_MODEL_IDENTIFIER>
```

For example, if OpenRouter exposes a native model identifier such as:

```text
anthropic/some-model
```

Azathoth identifies it as:

```text
openrouter/anthropic/some-model
```

Use the identifiers printed by your own `model list` output rather than copying
an identifier from this guide.

Provider catalogs change over time.

## 7. Inspect a Model

Choose an identifier returned by:

```bash
azathoth model list
```

Then inspect it:

```bash
azathoth model show <MODEL_IDENTIFIER>
```

The CLI renders provider-neutral metadata including information such as:

```text
ID
Provider
Model
Name
Input Modalities
Output Modalities
Capabilities
Context Window
Maximum Output
Pricing
```

The exact metadata available depends on current provider state.

## 8. Authorize a Model

Current provider availability and organizational authorization are separate.

Before a portfolio-selected workflow can use a model, authorize a currently
available model:

```bash
azathoth model authorize <MODEL_IDENTIFIER>
```

On success:

```text
Authorized model <MODEL_IDENTIFIER>.
```

Inspect the durable portfolio:

```bash
azathoth model portfolio
```

The authorized identifier should now be listed.

The distinction is:

```text
azathoth model list
        │
        ▼
what providers currently expose


azathoth model portfolio
        │
        ▼
what this Azathoth installation authorizes
```

Authorization does not create provider availability.

A model must currently exist before it can be newly authorized.

## 9. Optionally Authorize Multiple Models

Azathoth's model-substitution optimizer becomes more interesting when multiple
compatible models are available for empirical comparison.

You may authorize additional text-capable models from `model list`:

```bash
azathoth model authorize <SECOND_MODEL_IDENTIFIER>
azathoth model authorize <THIRD_MODEL_IDENTIFIER>
```

Then inspect the portfolio:

```bash
azathoth model portfolio
```

This is optional for basic workflow execution.

At least one compatible current, authorized, executable model is required for
the canonical portfolio-selected prompt workflow.

## 10. Run the Configured Workflow

Execute the configured workflow:

```bash
azathoth workflow run \
    11111111-1111-1111-1111-111111111111
```

This follows the configured execution path:

```text
WorkflowSpecification
        │
        ▼
runtime candidate generation
        │
        ▼
WorkflowCandidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

The CLI renders recorded execution evidence.

A successful prompt-backed step may include:

```text
Strategy
Provider
Model
Prompt Tokens
Completion Tokens
Total Tokens
Latency
Estimated Cost
Output
```

The exact language-model response is not predetermined.

This is a live provider-backed workflow.

Record the output if you want to use it as the expected value in the next
section.

### `run` Is Not Production Invocation

This command:

```bash
azathoth workflow run <WORKFLOW_ID>
```

executes the currently configured workflow.

It does not require the workflow to be deployed.

It does not execute `WorkflowProductionState`.

```text
workflow run
    configured execution
```

Production execution uses a different command later in this guide.

## 11. Run an Empirical Optimization Session

Azathoth exposes empirical optimization through:

```bash
azathoth workflow optimize <WORKFLOW_ID> \
    --expected '<JSON>' \
    --target-latency <SECONDS> \
    --target-cost <USD>
```

For example, if the output you want to treat as expected behavior is the JSON
string:

```text
"example response"
```

you could run:

```bash
azathoth workflow optimize \
    11111111-1111-1111-1111-111111111111 \
    --expected '"example response"' \
    --target-latency 5 \
    --target-cost 0.01
```

The quoting matters.

`--expected` is parsed as JSON.

Therefore:

```bash
--expected '"example response"'
```

means a JSON string, while:

```bash
--expected '{"status":"success"}'
```

means a JSON object.

Invalid JSON is rejected.

### Multiple Generations

The default optimization generation count is:

```text
1
```

To request more:

```bash
azathoth workflow optimize \
    11111111-1111-1111-1111-111111111111 \
    --expected '"example response"' \
    --target-latency 5 \
    --target-cost 0.01 \
    --generations 3
```

### What Optimization Does

The CLI constructs:

```text
ExpectedOutcome
    exact comparison

WorkflowScoringPolicy
    target latency
    target cost
```

and runs the configured workflow through the empirical optimization lifecycle.

Conceptually:

```text
configured workflow
       │
       ▼
candidate generation
       │
       ▼
execution
       │
       ▼
exact evaluation
       │
       ▼
workflow scoring
       │
       ▼
ranking
       │
       ▼
optimizer
       │
       ▼
next candidate generation
```

If the portfolio contains eligible models with comparable pricing, the
model-substitution optimizer may generate strictly cheaper legal alternatives.

Those alternatives are not automatically considered better.

They must be executed and evaluated.

### Optimization Does Not Deploy

This is a critical V1 boundary:

```text
workflow optimize
        ≠
workflow promote
```

Running optimization does not change active production state.

Even if an empirical candidate wins, production remains unchanged until an
explicit promotion occurs.

## 12. Promote the Configured Workflow

Promote the configured workflow explicitly:

```bash
azathoth workflow promote \
    11111111-1111-1111-1111-111111111111
```

Promotion performs:

```text
configured WorkflowSpecification
        │
        ▼
candidate generation
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

For portfolio-selected prompt steps, the generated candidate's chosen model is
materialized into fixed production model intent.

The promotion output includes the workflow ID, revision ID, and production model
selection.

### State Versus Revision

Promotion creates two distinct artifacts.

```text
WorkflowProductionState
    current production execution authority

WorkflowProductionRevision
    immutable audit history
```

A revision does not become production authority merely because it is the newest
revision.

Production executes current state.

## 13. Invoke Production

The workflow is now eligible for production invocation.

Invoke it with:

```bash
azathoth workflow invoke \
    11111111-1111-1111-1111-111111111111 \
    --input '{"request":"hello from production"}'
```

The input must be valid JSON.

Production invocation creates an immutable initial context event containing:

```text
{
    "input": <caller JSON>
}
```

and records a durable `ProductionInvocation`.

The path is:

```text
caller JSON
    │
    ▼
ProductionInvocation
    │
    ▼
WorkflowProductionState
    │
    ▼
WorkflowRun
    │
    ▼
ProductionInvocationResult
```

Successful output includes:

```text
Invocation ID
Status: succeeded
Result
```

### A Note About the Canonical Example Input

The checked-in `simple-prompt.json` example intentionally has no workflow input
bindings.

Its prompt is:

```text
Answer the request concisely.
```

Therefore the production input supplied above is still correctly recorded in
the production invocation context, but this particular example does not bind
that value into the prompt.

That is intentional.

The example exists primarily to demonstrate the smallest complete durable
prompt-backed workflow.

Real applications can define context and workflow bindings that consume runtime
input.

## 14. Understand `run` Versus `invoke`

You have now exercised both execution paths.

```text
azathoth workflow run
        │
        ▼
configured WorkflowSpecification
        │
        ▼
generate current candidate
        │
        ▼
WorkflowRun
```

versus:

```text
azathoth workflow invoke
        │
        ▼
WorkflowProductionState
        │
        ▼
production execution
        │
        ▼
ProductionInvocation
        +
WorkflowRun
```

The difference is authority.

`run` asks:

> What does the currently configured workflow do in this runtime?

`invoke` asks:

> What does production currently say this workflow should do?

## 15. Understand `optimize` Versus `promote`

The second critical distinction is:

```text
workflow optimize
        │
        ▼
empirical evidence and candidate search
```

versus:

```text
workflow promote
        │
        ▼
explicit production state transition
```

Azathoth does not let optimization silently deploy itself.

That separation is central to the OSS V1 architecture.

## 16. Inspect the Resulting Durable Lifecycle

After completing the guide, your temporary database contains durable state
representing multiple parts of the lifecycle:

```text
WorkflowSpecification
        │
        ├── configured workflow
        │
        ▼
ModelPortfolio
        │
        ├── organizational authorization
        │
        ▼
WorkflowProductionState
        │
        ├── current production authority
        │
        ▼
WorkflowProductionRevision
        │
        ├── deployment audit history
        │
        ▼
ProductionInvocation
        │
        ├── external production call
        │
        ▼
WorkflowRun
        │
        └── empirical execution evidence
```

These are not interchangeable records.

Each represents a different architectural fact.

## 17. Clean Up

Because this walkthrough used a temporary database directory, remove it when
finished:

```bash
rm -rf "$AZATHOTH_QUICKSTART_DIR"
unset AZATHOTH_QUICKSTART_DIR
unset AZATHOTH_DATABASE
```

Optionally remove the OpenRouter key from the current shell:

```bash
unset OPENROUTER_API_KEY
```

## What You Just Proved

In one CLI journey, you exercised Azathoth's major OSS V1 boundaries:

```text
portable workflow definition
        │
        ▼
durable configuration
        │
        ▼
current provider discovery
        │
        ▼
organizational model authorization
        │
        ▼
runtime candidate generation
        │
        ▼
configured execution
        │
        ▼
empirical optimization
        │
        ▼
explicit production promotion
        │
        ▼
active production invocation
        │
        ▼
durable execution evidence
```

More importantly, you exercised the separations that make those operations
trustworthy:

```text
availability
    ≠
authorization

configuration
    ≠
execution

execution
    ≠
evaluation

optimization
    ≠
promotion

promotion revision
    ≠
production authority

configured execution
    ≠
production invocation
```

That is the core Azathoth V1 operating model.

## Where to Go Next

For the complete system architecture, return to:

```text
README.md
```

For individual subsystem details:

```text
src/azathoth/cli/README.md
src/azathoth/context/README.md
src/azathoth/evaluation/README.md
src/azathoth/execution/README.md
src/azathoth/goals/README.md
src/azathoth/optimization/README.md
src/azathoth/prompting/README.md
src/azathoth/providers/README.md
src/azathoth/runtime/README.md
src/azathoth/strategies/README.md
src/azathoth/tools/README.md
src/azathoth/workflows/README.md
```

Architectural decisions are recorded under:

```text
docs/adrs/
```

Run the complete development quality gate with:

```bash
make check
```