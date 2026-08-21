# Providers

`azathoth.providers` defines the provider-neutral language model infrastructure used by Azathoth.

It separates model capabilities, pricing, discovery, and execution from any specific vendor implementation.

The provider package answers two different questions:

> Which configured models are eligible for this workload?

and:

> Which executable language model implementation should handle the request?

Those responsibilities are intentionally separate.

## Purpose

Model-backed strategies should not hard-code assumptions about:

- provider names;
- model names;
- pricing;
- context windows;
- modalities;
- capabilities; or
- runtime client implementations.

Instead, workloads declare what they require.

Azathoth then discovers eligible models from a catalog and resolves executable implementations from a registry.

```text
Workload Requirements
        │
        ▼
    ModelQuery
        │
        ▼
   ModelCatalog
        │
        ▼
 Eligible Models
        │
        ▼
LanguageModelRegistry
        │
        ▼
Executable Model
```

This keeps optimization and workflow logic independent from provider-specific code.

## LanguageModel Protocol

Executable language model implementations satisfy the `LanguageModel` protocol.

```python
from azathoth.providers import (
    ModelResponse,
    Prompt,
)


class LanguageModel:
    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse: ...
```

A concrete implementation may call:

- a hosted API;
- a local model;
- a test double;
- a gateway;
- or any future model runtime.

Higher-level Azathoth code only depends on the protocol.

## OpenRouterLanguageModel

`OpenRouterLanguageModel` is the first production implementation of the
`LanguageModel` protocol.

```text
Prompt
   │
   ▼
OpenRouterLanguageModel
   │
   ▼
OpenRouter
   │
   ▼
ModelResponse
```

The implementation maps provider-neutral prompts onto the OpenRouter chat
completion API.

Responses are translated into immutable `ModelResponse` objects so higher-level
execution, evaluation, and optimization remain provider independent.

## Workflow Integration

OpenRouter integrates through the existing provider abstraction.

```text
WorkflowRunner
       │
       ▼
PromptStrategy
       │
       ▼
LanguageModel
       │
       ▼
OpenRouterLanguageModel
       │
       ▼
OpenRouter
```

The provider package remains responsible only for model execution.

Workflow orchestration, execution history, evaluation, and optimization remain
outside the provider layer.

## ModelExecutor

`ModelExecutor` executes durable model requests through executable language
models.

```text
ModelRequest
      │
      ▼
ModelExecutor
      │
      ▼
LanguageModel
      │
      ▼
ModelResponse
```

The executor bridges durable request models to the existing prompt-based
provider protocol.

This allows request models to evolve independently from provider
implementations.

Unsupported execution controls are rejected explicitly rather than ignored.

## Prompt

`Prompt` represents the rendered request supplied to a language model.

```python
from azathoth.providers import Prompt

prompt = Prompt(
    text="Return exactly success.",
)
```

Prompts are immutable.

Prompt construction belongs to the prompting package.

The provider layer only receives rendered prompts ready for execution.

## Model Request Execution

Provider-neutral execution now proceeds through a `ModelExecutor`.

```text
ModelRequest
      │
      ▼
ModelExecutor
      │
      ▼
LanguageModel
      │
      ▼
ModelResponse
```

The executor bridges durable request models to executable language model
implementations.

Current language model implementations continue to execute rendered prompts,
preserving compatibility with the existing provider protocol.

## ModelRequest

`ModelRequest` represents a durable execution request for a rendered prompt.

```python
from azathoth.providers import (
    ModelRequest,
    Prompt,
)

request = ModelRequest(
    prompt=Prompt(
        text="Return exactly success.",
    ),
)
```

A model request packages:

- the rendered prompt; and
- optional provider-neutral execution parameters.

Current execution supports prompt-only requests.

Advanced generation controls are intentionally rejected until supported by
provider implementations.

Model requests establish a stable execution boundary for future provider
integrations while preserving compatibility with the existing language model
protocol.

## ModelResponse

Language model execution returns a `ModelResponse`.

```python
from azathoth.providers import ModelResponse

response = ModelResponse(
    text="success",
    provider="example-provider",
    model="example-model",
    prompt_tokens=10,
    completion_tokens=1,
    total_tokens=11,
    latency_ms=100,
    estimated_cost_usd=0.001,
)
```

A response records:

- generated text;
- provider;
- model;
- prompt token count;
- completion token count;
- total token count;
- latency; and
- estimated cost.

These measurements are provider-neutral so downstream execution and optimization code can compare models consistently.

## Model Metadata

`ModelMetadata` describes one configured model.

```python
from azathoth.providers import ModelMetadata

model = ModelMetadata(
    provider="example-provider",
    model="example-model",
    display_name="Example Model",
    context_window_tokens=128_000,
)
```

Metadata may describe:

- provider;
- model identifier;
- display name;
- supported input modalities;
- supported output modalities;
- capabilities;
- context window;
- maximum output tokens; and
- pricing.

The provider-qualified identifier is derived from:

```text
provider/model
```

For example:

```text
example-provider/example-model
```

This identifier is used consistently across catalogs, registries, model bindings, and candidate generation.

## Model Modalities

Models declare supported input and output modalities.

Current modality types include:

- text;
- image;
- audio; and
- video.

```text
ModelMetadata
├── input_modalities
└── output_modalities
```

Workloads can require particular modalities without knowing which provider satisfies them.

## Model Capabilities

Models may also advertise discrete capabilities.

Current capabilities include:

- structured output;
- tool use;
- vision; and
- streaming.

A workload can require any subset of these capabilities.

```text
Required Capabilities
        │
        ▼
    ModelQuery
        │
        ▼
Eligible ModelMetadata
```

## Model Pricing

Optional `ModelPricing` records configured token pricing.

```python
from azathoth.providers import ModelPricing

pricing = ModelPricing(
    input_usd_per_million_tokens=1.0,
    output_usd_per_million_tokens=4.0,
)
```

Pricing is expressed per million tokens for consistent comparison.

Pricing data is configuration, not live billing data.

Azathoth uses it to reason about workload eligibility and future cost-aware optimization.

## ModelRequirements

Model-backed workloads declare provider-neutral requirements using `ModelRequirements`.

```python
from azathoth.providers import (
    ModelCapability,
    ModelRequirements,
)

requirements = ModelRequirements(
    required_capabilities=frozenset(
        {
            ModelCapability.STRUCTURED_OUTPUT,
        }
    ),
    minimum_context_window_tokens=32_000,
)
```

Requirements can constrain:

- required capabilities;
- input modalities;
- output modalities;
- minimum context window;
- minimum output size;
- maximum input price;
- maximum output price; and
- whether pricing must be known.

This is one of the most important abstractions in the provider package.

The workload says:

> I need a model with these characteristics.

It does not say:

> Use this specific vendor model.

## ModelQuery

`ModelQuery` performs discovery against model metadata.

Queries may be created directly or derived from workload requirements.

```python
from azathoth.providers import ModelQuery

query = ModelQuery.from_requirements(
    requirements,
)
```

A query can additionally restrict providers:

```python
query = ModelQuery.from_requirements(
    requirements,
    providers=frozenset(
        {
            "example-provider",
        }
    ),
)
```

Queries remain pure domain objects.

They do not perform network calls or instantiate provider clients.

## ModelCatalog

`ModelCatalog` is an immutable inventory of configured models.

```python
from azathoth.providers import ModelCatalog

catalog = ModelCatalog(
    models=(
        model_a,
        model_b,
        model_c,
    ),
)
```

The catalog supports:

- lookup by provider-qualified identifier;
- discovery by provider;
- provider enumeration; and
- requirement-based filtering.

```python
eligible_models = catalog.find(query)
```

Catalog order is preserved.

This becomes important when higher-level systems deliberately use configured model order as a deterministic selection policy.

## Model Persistence

Configured model metadata can be persisted outside application source.

`ModelRepository` provides the storage-neutral persistence boundary.

Current implementations include:

- `InMemoryModelRepository`; and
- `SQLiteModelRepository`.

```text
ModelMetadata
      │
      ▼
ModelRepository
      │
      ├── InMemoryModelRepository
      └── SQLiteModelRepository
```

Repositories persist `ModelMetadata`, not executable language model
implementations.

### Model Catalog Reconstruction

`ModelCatalogLoader` reconstructs an immutable `ModelCatalog` from repository
state.

```text
ModelRepository
      │
      ▼
ModelCatalogLoader
      │
      ▼
ModelCatalog
```

Repository order becomes catalog order.

This preserves deterministic discovery behavior across process restarts.

### Persisted Versus Runtime State

Model persistence records configured model knowledge.

```text
persisted
├── provider
├── model identity
├── modalities
├── capabilities
├── context limits
└── pricing
```

Provider runtime objects remain process-local.

```text
runtime
├── provider credentials
├── HTTP clients
├── transports
├── LanguageModel implementations
└── LanguageModelRegistry
```

Provider credentials are not persisted by `ModelRepository`.

For OpenRouter, reconstructed model metadata can be combined with runtime
provider configuration after restart.

```text
SQLiteModelRepository
        │
        ▼
ModelCatalogLoader
        │
        ▼
ModelCatalog
        │
        +
OpenRouterConfiguration
        │
        ▼
OpenRouterModelRegistryLoader
        │
        ▼
LanguageModelRegistry
```

This preserves the separation between model knowledge and provider access.

## Catalog Versus Registry

Azathoth intentionally separates model metadata from executable implementations.

```text
ModelCatalog
    │
    │ describes
    ▼
ModelMetadata

LanguageModelRegistry
    │
    │ resolves
    ▼
LanguageModel
```

The catalog answers:

> What models are available and what can they do?

The registry answers:

> Which executable implementation corresponds to this model identifier?

This distinction prevents runtime provider objects from leaking into immutable configuration models.

## LanguageModelRegistry

`LanguageModelRegistry` maps provider-qualified identifiers to executable language model implementations.

```python
from azathoth.providers import LanguageModelRegistry

registry = LanguageModelRegistry(
    {
        "example-provider/example-model": language_model,
    }
)
```

Models are resolved using the same identifier exposed by `ModelMetadata`.

```python
language_model = registry.get("example-provider/example-model")
```

A catalog entry without a corresponding registry entry is valid configuration, but it cannot become an executable candidate.

This allows Azathoth to distinguish:

- known models;
- eligible models; and
- executable models.

## Registry Composition

Executable language model registries can be composed.

```python
registry = LanguageModelRegistry.compose(
    (
        openrouter_registry,
        local_registry,
        other_registry,
    )
)
```

Composition preserves registry and model order.

Provider-qualified model identifiers must remain unique across the combined
registries.

```text
Registry A
├── provider-a/model-1
└── provider-a/model-2

Registry B
├── provider-b/model-3
└── provider-b/model-4

        │
        ▼
     compose
        │
        ▼
Combined Registry
├── provider-a/model-1
├── provider-a/model-2
├── provider-b/model-3
└── provider-b/model-4
```

Source registries remain unchanged.

Registry composition introduces no model-selection policy.

## OpenRouter Configuration

`OpenRouterConfiguration` records the immutable configuration required to
communicate with the OpenRouter API.

Configuration includes:

- API key;
- base URL; and
- request timeout.

Sensitive credentials are represented using `SecretStr` to reduce accidental
exposure through logging or serialization.

## Multi-Model Live Verification

Multi-model OpenRouter execution has optional live verification.

Live tests remain disabled by default and consume no provider credits during
normal development or CI.

```text
AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1
```

The multi-model smoke test reads a comma-separated test population from:

```text
OPENROUTER_TEST_MODELS
```

For example:

```text
provider/model-a,provider/model-b
```

This variable configures only the opt-in live test population.

It is not a production model-selection mechanism.

## Multi-Model OpenRouter Runtime

One `OpenRouterConfiguration` can back multiple executable OpenRouter models.

`OpenRouterModelRegistryLoader` creates runtime registrations for the
OpenRouter models present in a `ModelCatalog`.

```text
OpenRouterConfiguration
          +
     ModelCatalog
          │
          ▼
OpenRouterModelRegistryLoader
          │
          ▼
LanguageModelRegistry
├── openrouter/model-a
├── openrouter/model-b
└── openrouter/model-c
```

Provider configuration supplies API access.

It does not select one global OpenRouter model.

Each model remains independently identified by its provider-qualified model
identifier.

The resulting OpenRouter registry can also be composed with registries from
other providers.

```text
OpenRouter Registry
        +
Other Provider Registry
        │
        ▼
LanguageModelRegistry.compose(...)
        │
        ▼
Unified Executable Runtime
```

### Durable OpenRouter Model Catalogs

OpenRouter model metadata may be reconstructed from a `ModelRepository` before
runtime assembly.

```text
SQLite
  │
  ▼
ModelCatalog
  │
  ▼
OpenRouterModelRegistryLoader
  │
  ▼
multiple executable OpenRouter models
```

The reconstructed catalog retains configured model identity, capabilities,
pricing, and deterministic order.

The OpenRouter API key remains runtime configuration and is not stored with the
model catalog.

### Per-Workload Selection

Model selection remains driven by workload requirements.

```text
ModelRequirements
        │
        ▼
    ModelCatalog
        │
        ▼
eligible models
        │
        ▼
LanguageModelRegistry
        │
        ▼
executable candidates
```

For example, one workload may require inexpensive models while another requires
structured-output capability.

```text
cheap workload
      │
      ▼
cheap OpenRouter model

structured workload
      │
      ▼
structured-output OpenRouter model
```

No OpenRouter-specific model name needs to be embedded in the workload
specification.

### Requested and Resolved Models

OpenRouter responses preserve both the configured model and the model identity
reported by OpenRouter.

```text
ModelResponse.model
    configured model

ModelResponse.resolved_model
    OpenRouter-reported model
```

This is useful when OpenRouter resolves aliases or routed model identifiers to
a concrete served model.

## DeterministicLanguageModel

The provider package includes a deterministic language model implementation for
testing and local execution.

```python
from azathoth.providers import (
    DeterministicLanguageModel,
    Prompt,
)

model = DeterministicLanguageModel()

response = await model.complete(
    Prompt(
        text="Hello",
    )
)
```

The deterministic implementation satisfies the `LanguageModel` protocol without
performing any network communication.

It provides repeatable execution for unit tests, integration tests, and
end-to-end workflow verification.

Future provider implementations, including OpenRouter, will satisfy the same
protocol.

## Discovery and Execution

The complete provider flow looks like this:

```text
ModelRequirements
        │
        ▼
    ModelQuery
        │
        ▼
   ModelCatalog
        │
        ▼
 ModelMetadata
        │
        ▼
provider/model identifier
        │
        ▼
LanguageModelRegistry
        │
        ▼
LanguageModel
   ┌───────────────┐
   ▼               ▼
Deterministic   OpenRouter
        ▲
        │
 ModelExecutor
        ▲
        │
 ModelRequest
        │
        ▼
     Prompt
        │
        ▼
 ModelResponse
```

Each stage has one responsibility.

## Provider Independence

Provider independence is a core Azathoth design principle.

Higher-level code should not need to know whether execution uses:

- OpenAI;
- Anthropic;
- Google;
- a local model;
- an internal gateway;
- or a future provider that does not exist yet.

As long as the implementation satisfies `LanguageModel`, it can participate in the same execution and optimization infrastructure.

## Selection Is Not Execution

Model discovery and model execution are intentionally separate.

The catalog may identify several eligible models.

```text
requirements
    │
    ▼
model A
model B
model C
```

Candidate generation decides which of those models should become executable strategies.

The registry then supplies their runtime implementations.

The provider package itself does not decide which candidate should win.

That responsibility belongs to higher-level experimentation and optimization.

## Design Principles

The provider domain is intentionally:

- provider neutral;
- immutable where configuration is concerned;
- explicit about capabilities;
- explicit about pricing;
- separate from runtime implementations;
- deterministic during discovery; and
- independent of workflow and optimization policy.

Providers describe and execute models.

They do not evaluate outputs, score workflows, rank candidates, or optimize populations.

## Relationship to Other Packages

[`azathoth.prompting`](../prompting/README.md) uses model requirements, catalogs, registries, prompts, and language models to construct executable prompt strategies.

[`azathoth.strategies`](../strategies/README.md) provides the common execution abstraction that model-backed strategies implement.

[`azathoth.execution`](../execution/README.md) records provider-neutral metrics returned by model-backed strategies.

[`azathoth.workflows`](../workflows/README.md) uses provider discovery indirectly when generating executable workflow candidates.

[`azathoth.optimization`](../optimization/README.md) can compare model-backed strategies and workflows using quality, latency, and cost evidence without depending on a specific provider.

See the [project README](../../../README.md) for the complete Azathoth architecture.