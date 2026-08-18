# Prompting

`azathoth.prompting` provides language-model-backed strategy implementations, prompt templates, model bindings, and prompt candidate generation.

The prompting package sits between Azathoth's provider-neutral model infrastructure and the common strategy abstraction.

It answers two related questions:

> How should a prompt be constructed?

and:

> How should that prompt become an executable strategy bound to a model?

## Purpose

Prompt-backed behavior involves several concerns that should remain separate:

- prompt specification;
- context-aware rendering;
- model requirements;
- model discovery;
- executable model binding;
- candidate generation; and
- response validation.

Azathoth keeps those concerns explicit instead of collapsing them into one opaque model call.

```text
Prompt Specification
        │
        ▼
Model Requirements
        │
        ▼
Candidate Generation
        │
        ▼
Prompt Strategy
        │
        ▼
Language Model
        │
        ▼
Strategy Outcome
```

This allows prompts to participate in the same execution, experimentation, and optimization infrastructure as any other strategy.

## PromptStrategy

`PromptStrategy` executes an already-rendered prompt using a language model.

```python
from azathoth.prompting import PromptStrategy
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata

strategy = PromptStrategy(
    metadata=StrategyMetadata(
        name="answer-question",
        description="Answer a question using a language model.",
    ),
    prompt=Prompt(
        text="Return exactly success.",
    ),
    language_model=language_model,
)
```

`PromptStrategy` does not inspect runtime context before execution.

Its prompt is already complete.

This makes it especially useful for:

- reproducible experiments;
- prompt candidate comparison;
- optimization;
- deterministic candidate generation; and
- workflows whose prompt was resolved earlier.

## ContextPromptStrategy

`ContextPromptStrategy` renders a prompt from `Context` immediately before execution.

```text
Context
   │
   ▼
PromptTemplate
   │
   ▼
Rendered Prompt
   │
   ▼
LanguageModel
   │
   ▼
StrategyOutcome
```

This is useful when the prompt depends on values produced during live execution.

A context-aware strategy is created with a `PromptTemplate` rather than a pre-rendered `Prompt`.

```python
from azathoth.prompting import ContextPromptStrategy

strategy = ContextPromptStrategy(
    metadata=metadata,
    template=template,
    language_model=language_model,
)
```

When executed, the strategy resolves bindings against the supplied context before calling the language model.

## PromptStrategy Versus ContextPromptStrategy

Both classes implement the same strategy behavior at a high level, but they operate at different points in the prompt lifecycle.

```text
PromptStrategy

Rendered Prompt
      │
      ▼
LanguageModel
```

```text
ContextPromptStrategy

Context
   │
   ▼
PromptTemplate
   │
   ▼
Rendered Prompt
   │
   ▼
LanguageModel
```

Use `PromptStrategy` when the prompt is already known.

Use `ContextPromptStrategy` when prompt construction depends on runtime context.

This separation keeps prompt rendering explicit and independently testable.

## PromptTemplate

`PromptTemplate` describes text that may contain values resolved from context.

```python
from azathoth.prompting import (
    PromptBinding,
    PromptTemplate,
)

template = PromptTemplate(
    text="Answer this request: {request}",
    bindings=(
        PromptBinding(
            variable_name="request",
            event_type="request.received",
            field_name="text",
        ),
    ),
)
```

Templates are immutable.

Rendering a template produces a provider-level `Prompt`.

```python
prompt = template.render(context)
```

The template itself does not call a model.

## PromptBinding

A `PromptBinding` maps one template variable to a field in the latest matching context event.

```text
Prompt Variable
      │
      ▼
 Event Type
      │
      ▼
Latest ContextEvent
      │
      ▼
 Field Name
      │
      ▼
Rendered Value
```

For example:

```python
PromptBinding(
    variable_name="request",
    event_type="request.received",
    field_name="text",
)
```

resolves `{request}` from the `text` field of the latest `request.received` event.

## Binding Errors

Prompt rendering fails explicitly when required context is unavailable.

Current prompting errors include:

- `PromptBindingError`
- `PromptBindingEventNotFoundError`
- `PromptBindingFieldNotFoundError`

These failures are deterministic and occur before model execution.

This prevents malformed prompts from silently reaching providers.

## PromptStrategySpec

`PromptStrategySpec` describes a model-independent prompt strategy.

```python
from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)

specification = PromptStrategySpec(
    metadata=metadata,
    prompt=Prompt(
        text="Return exactly success.",
    ),
    model_requirements=ModelRequirements(),
)
```

A specification contains:

- strategy metadata;
- a rendered prompt; and
- provider-neutral model requirements.

It deliberately does **not** contain an executable language model.

This distinction is fundamental.

```text
PromptStrategySpec
        │
        │ model independent
        ▼
Candidate Generation
        │
        ▼
PromptStrategy
        │
        │ executable
        ▼
LanguageModel
```

Specifications are suitable for configuration, workflow descriptions, and optimization because they remain independent of runtime provider objects.

## Candidate Generation

`generate_prompt_candidates()` turns one prompt specification into executable prompt strategies.

```python
from azathoth.prompting import generate_prompt_candidates

candidates = generate_prompt_candidates(
    specification=specification,
    catalog=catalog,
    registry=registry,
)
```

Candidate generation follows this process:

```text
PromptStrategySpec
        │
        ▼
ModelRequirements
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
Executable Models
        │
        ▼
PromptStrategy Candidates
```

Only models that:

- satisfy the declared requirements; and
- have executable registry implementations

become candidates.

## Deterministic Candidate Identity

Generated prompt strategies receive deterministic identifiers.

Their IDs are derived from:

- the specification strategy ID; and
- the provider-qualified model identifier.

This means generating the same candidate from the same specification and model produces the same strategy identity.

Deterministic identity makes candidate generation reproducible across experiments.

## ModelBinding

Executable prompt strategies may record a `ModelBinding`.

```python
from azathoth.prompting import ModelBinding

binding = ModelBinding(
    identifier="example-provider/example-model",
)
```

The binding records which catalog model the strategy is expected to use.

After model execution, the binding validates that the reported provider and model match the configured identifier.

```text
Configured Binding
        │
        ▼
example-provider/example-model

ModelResponse
        │
        ▼
provider + model
        │
        ▼
validation
```

A mismatch raises `ModelBindingMismatchError`.

This prevents execution evidence from silently being attributed to the wrong configured model.

## Shared Prompt Execution

Both prompt strategy implementations ultimately use the same prompt execution behavior.

```text
Prompt
  │
  ▼
LanguageModel.complete()
  │
  ▼
ModelResponse
  │
  ▼
Binding Validation
  │
  ▼
StrategyExecutionMetrics
  │
  ▼
StrategyOutcome
```

Provider response metadata is translated into provider-neutral `StrategyExecutionMetrics`.

Those metrics include:

- provider;
- model;
- prompt tokens;
- completion tokens;
- total tokens;
- latency; and
- estimated cost.

This lets higher-level execution and optimization code compare prompt-backed strategies without knowing which provider produced the result.

## Specification Versus Execution

The prompting package deliberately separates three stages.

```text
Specification
     │
     ▼
Candidate Generation
     │
     ▼
Execution
```

### Specification

`PromptStrategySpec`

Describes:

- what prompt should run; and
- what kind of model is required.

### Candidate Generation

`generate_prompt_candidates()`

Determines:

- which configured models are eligible; and
- which eligible models have executable implementations.

### Execution

`PromptStrategy` or `ContextPromptStrategy`

Performs:

- prompt rendering when necessary;
- model completion;
- model binding validation; and
- metric translation.

Keeping these stages separate prevents provider runtime details from leaking into model-independent workflow specifications.

## Prompting and Optimization

Prompt strategies can participate in empirical comparison through Azathoth's
existing execution, evaluation, scoring, and ranking infrastructure.

Optimization policy remains outside the prompting package.

## Prompting and Workflows

Workflow step specifications currently use `PromptStrategySpec` as their model-independent executable specification.

```text
WorkflowStepSpecification
        │
        ▼
PromptStrategySpec
        │
        ▼
generate_prompt_candidates()
        │
        ▼
PromptStrategy
        │
        ▼
WorkflowCandidateStep
```

This allows workflows to describe prompt-backed steps without embedding live provider implementations.

Workflow generation later binds those specifications to executable models.

## Design Principles

The prompting domain is intentionally:

- strategy compatible;
- provider neutral at specification time;
- explicit about runtime model binding;
- deterministic during candidate generation;
- context aware when required;
- independently testable; and
- compatible with empirical optimization.

Prompting constructs and executes model-backed strategies.

It does not evaluate results, rank candidates, or decide which model or prompt is best.

Those responsibilities belong to higher-level experimentation and optimization.

## Relationship to Other Packages

[`azathoth.context`](../context/README.md) supplies runtime values used by `PromptTemplate` and `ContextPromptStrategy`.

[`azathoth.providers`](../providers/README.md) supplies model metadata, requirements, catalogs, registries, prompts, responses, and executable language models.

[`azathoth.strategies`](../strategies/README.md) defines the common executable strategy contract implemented by prompt-backed strategies.

[`azathoth.execution`](../execution/README.md) records prompt strategy execution results and provider-neutral metrics.

[`azathoth.workflows`](../workflows/README.md) uses `PromptStrategySpec` when defining model-independent workflow steps.

[`azathoth.optimization`](../optimization/README.md) can compare prompt-backed candidates using empirical evidence.

See the [project README](../../../README.md) for the complete Azathoth architecture.