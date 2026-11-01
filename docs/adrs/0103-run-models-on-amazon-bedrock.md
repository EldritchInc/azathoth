# ADR 0103: Run Models on Amazon Bedrock

- Status: Accepted
- Date: 2026-11-01
- Decided in: #120

## Context

Azathoth runs its models through OpenRouter, the only provider it has. That
suits a laptop. It does not suit Azathoth 1.1 on AWS, where a container
already holds AWS credentials, from the task role it runs under, and an
organization often wants its model traffic, its spending and its data
agreements to stay inside AWS. There, the provider is Amazon Bedrock.

The provider boundary was built for a second provider:

- Models are named `provider/model` everywhere, and nothing parses the model
  part.
- `ProviderModelDirectory` discovers a provider's current models as
  `ProviderModel` values, and `ProviderModelCatalogSynchronizer` already
  combines any number of them into one catalog.
- `LanguageModel` is one method, `complete`, and `LanguageModelRegistry`
  already composes the registries of several providers.

Bedrock differs from OpenRouter in five ways that matter here:

- Its credentials are not a key in a variable. They come from AWS's own
  chain: environment variables, a profile, SSO, the ECS task role, a web
  identity, or a Bedrock API key. A process cannot tell, without asking
  AWS, whether it has any.
- It is regional. The models a region offers differ, and some, including the
  newer Claude models, can only be called through an inference profile, such
  as `us.anthropic.…` or `global.anthropic.…`, which routes the call across
  regions.
- Its model listing reports no prices and no context windows, and its
  replies report no cost. AWS's Price List API does not fill the gap: newer
  models are missing from it, or listed under another service code.
- One API, Converse, calls every chat model with the same request and reply.
- It can refuse an answer: a guardrail can intervene, or content can be
  filtered, and the reply still arrives as text.

## Decision

### Turning Bedrock on

Bedrock support is an optional extra, as tracing and PostgreSQL are:

```bash
python -m pip install "azathoth-ai[bedrock]"
export AZATHOTH_BEDROCK=1
```

The extra installs boto3. `AZATHOTH_BEDROCK` turns Bedrock on, with the
same values as `AZATHOTH_OTEL` (`1`, `true`, `yes`, `on`). It is a separate
switch because credentials alone cannot say whether Bedrock is meant: a
container may hold a task role for other reasons.

OpenRouter stays as it is, on when `OPENROUTER_API_KEY` is set. Either, both
or neither may be on. A process with neither has no models, as today.

boto3 is imported only when Bedrock is on, so installing the extra changes
nothing for anyone who does not turn it on.

### Credentials and region

Azathoth reads no AWS credentials of its own. boto3 finds them, in its own
order, and finds the region the same way: `AWS_REGION`, `AWS_DEFAULT_REGION`
or the profile. On Fargate, both come from the task: its role, and the
`AWS_REGION` ECS sets.

A process uses one region. Inference profiles reach the others.

A command with Bedrock on fails before it runs anything, with exit status 1,
when the extra is missing or no region is configured:

```text
AZATHOTH_BEDROCK is set, but boto3 is not installed; install azathoth-ai[bedrock].
AZATHOTH_BEDROCK is set, but no AWS region is configured; set AWS_REGION.
```

boto3 calls are blocking, so `complete` runs them in a worker thread with
`asyncio.to_thread`. Requests use botocore's `standard` retry mode, with 3
attempts, which retries throttling, and the same 30-second read timeout as
OpenRouter.

### Identity

A Bedrock model is named by its Bedrock ID, under the provider `bedrock`:

```text
bedrock/amazon.nova-pro-v1:0
bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0
```

The ID may hold dots and colons, but never `/`, so it fits `provider/model`
as every other identifier does, and promotion, the portfolio and model
bindings need no change.

Converse does not report which region served a call, so `resolved_model` is
not set.

### Discovery

`BedrockModelDirectory` lists, as `ProviderModel` values:

- every foundation model whose lifecycle is `ACTIVE`, that outputs text, and
  that can be called on demand, by its model ID;
- every `SYSTEM_DEFINED` inference profile that is `ACTIVE`, by its profile
  ID, with the modalities of the model it routes to.

It leaves out legacy models, models that serve only provisioned throughput,
and the inference profiles an organization creates itself, whose identifiers
are ARNs and hold `/`. Those can be added by a later decision.

Input and output modalities are mapped to Azathoth's. A model that can
stream its reply is marked `streaming`. Context windows are unknown, and
stay `None`. Prices come from the pricing document, below.

Discovery calls `ListFoundationModels` and `ListInferenceProfiles`, following
every page, each time the runtime is composed, as OpenRouter discovery does,
and records observations the same way.

### Execution

`BedrockLanguageModel` calls Converse with the prompt as one user message,
and no inference settings: `ModelExecutor` still rejects temperature and
maximum output tokens for every provider, until a decision supports them
everywhere.

Its reply is:

- the text blocks of the reply's message, in order, joined; other blocks,
  such as reasoning, are not part of the answer;
- the input and output tokens from `usage`, and their sum as the total,
  as step metrics require;
- the latency Bedrock reports, in `metrics.latencyMs`;
- the cost, from the pricing document.

A reply that stopped because a guardrail intervened, or because its content
was filtered, is a failed call, and raises `ModelExecutionError`: a blocked
answer must never be scored, or passed on, as an answer. A reply that stopped
at the maximum number of tokens is an answer, as it is from OpenRouter.

Every AWS error, after botocore's retries, raises `ModelExecutionError`
naming the model and AWS's error code, such as `AccessDeniedException` or
`ThrottlingException`, so the step's own retry and failure policies apply.

### Pricing

Bedrock's prices are given by the operator, in a pricing document named by
`AZATHOTH_BEDROCK_PRICING`:

```json
{
  "version": 1,
  "models": {
    "amazon.nova-pro-v1:0": {
      "input_usd_per_million_tokens": 0.8,
      "output_usd_per_million_tokens": 3.2
    }
  }
}
```

The figures are an example; an operator copies theirs from AWS's pricing
for their region. A model is keyed by its Bedrock ID. A priced model that
the region does not offer is ignored, so one document can serve several
regions.

The document is read once, when the runtime is composed. One that cannot be
read, or is not a valid pricing document, fails the command before it runs
anything, with exit status 1:

```text
AZATHOTH_BEDROCK_PRICING <PATH> is not a valid Bedrock pricing document: <REASON>.
```

A Bedrock model's cost is its tokens at its document's prices. A model the
document does not price has unknown pricing.

### Unknown cost

`ModelResponse.estimated_cost_usd` becomes optional: `None` means the cost is
unknown, never free. Step metrics already record cost as optional, and
tracing already leaves out an attribute that has no value.

What reads cost keeps its current rules:

- scoring a benchmark run needs every step's cost, and fails naming the
  model whose cost is unknown, and how to price it;
- a model with unknown pricing is never substituted as the cheaper model
  (ADR 0051), and a model query that requires known pricing excludes
  it;
- an unpriced semantic judge adds nothing to a judging cost total, as a
  judge call that raised already does.

A workflow over an unpriced model still runs, invokes and is traced.

### Discovery failures

A provider whose models cannot be discovered fails every command that
composes the runtime, with one line on stderr and exit status 1, for
OpenRouter as for Bedrock. Today a `ModelDiscoveryError` ends in a
traceback. A catalog is never composed without a provider that is on: a
provider that silently drops out leaves its models' workflows to fail later,
where the reason is harder to see.

As with an unusable database (ADR 0102), `job run` then prints no result,
because the fault is in the process, not the request.

### Child workflows

A process tool receives only the variables it grants (ADR 0099), so a child
workflow could not see Bedrock's configuration. The standard composition
tools grant `AZATHOTH_BEDROCK`, `AZATHOTH_BEDROCK_PRICING` and `AWS_*`
beside their existing grants, as implementations 1.0.3 and 1.1.3: the next
revisions of the same tool versions, for the reason ADR 0099 gives for its
own grants. `AWS_*` covers the region, profile, keys, container credentials,
web identity and Bedrock API key; `HOME`, where profiles are kept, is in
every tool's base environment already.

### The image

The container image (ADR 0101) installs the `bedrock` extra beside `otel`
and `postgres`. Bedrock stays off until `AZATHOTH_BEDROCK` is set. The image
gains botocore's size, roughly 100 MB, because AWS is where 1.1 runs.

### Verified without AWS

Bedrock is reached through a small `BedrockClient` protocol, holding the
three calls Azathoth makes, so every test of discovery, execution, pricing
and failures runs against a fake client, with no network and no account.
Live tests run only with `AZATHOTH_RUN_LIVE_BEDROCK_TESTS=1` and a
`BEDROCK_TEST_MODEL`, as OpenRouter's do, and are not part of the
deterministic gate.

### Not decided here

- Organization-created inference profiles, and provisioned throughput.
- Temperature, maximum output tokens and other inference settings, for every
  provider.
- Recording prices durably, with revisions, through the CLI.
- Images, documents and other inputs (Azathoth 1.2).
- More than one region in one process.

## Consequences

### Positive

- Azathoth runs its models on AWS with the credentials its container already
  has, and no other secret.
- Workflows mix OpenRouter and Bedrock models freely, by identifier, and an
  optimizer may substitute one provider's model for the other's.
- Cost is never invented: a model is priced by its operator, or its cost is
  unknown, and benchmarks say so.
- Nothing changes for anyone who leaves Bedrock off.

### Negative

- Bedrock's prices must be kept by hand, and go stale when AWS changes them.
- A workflow over an unpriced Bedrock model cannot be scored in a benchmark
  until its model is priced.
- Discovery adds two control-plane calls to every command that composes the
  runtime.
- The standard tools hand every child workflow the parent's AWS credentials,
  as they already hand it the OpenRouter key.
- The image is larger.

## Alternatives Considered

### aiobotocore, or signing requests over httpx

Rejected. AWS's credential chain, with task roles, SSO and web identity, is
the hard part of calling AWS, and boto3 is what AWS maintains for it. Calls
in a worker thread are enough at the concurrency a step reaches.

### Turning Bedrock on by its credentials, or by a region variable

Rejected. Credentials may be present for other reasons, and finding them
means asking AWS. A region variable of Azathoth's own would duplicate AWS's,
which Fargate already sets.

### A price table in the package

Rejected. It would be wrong for some region, and for every model, after the
next price change, with no sign that it was.

### AWS's Price List API

Rejected. It lacks newer models, splits others across service codes, and
names models differently from their IDs.

### Treating unknown cost as zero

Rejected. An unpriced model would look free, and every optimization that
weighs cost would prefer it.

### Leaving out a provider whose discovery fails

Rejected. The workflows of its models would fail later, at resolution, with
nothing to say that a provider had dropped out.
