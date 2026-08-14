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
        │
        ▼
   complete()
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