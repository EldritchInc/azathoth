# ADR 0013: Centralize Validated Prompt Execution

- Status: Accepted
- Date: 2026-08-03

## Context

Azathoth supports multiple prompt-backed strategy types.

Some strategies execute an already-rendered prompt, while others first render a prompt from context before execution.

Although these strategies differ in how prompts are produced, they share identical execution responsibilities:

- invoke a language model
- validate the configured model binding
- collect execution metrics
- produce a strategy outcome

Duplicating this execution logic across multiple strategy implementations risks behavioral drift as new capabilities such as retries, streaming, tracing, or tool invocation are introduced.

## Decision

Prompt-backed strategies will share a centralized execution implementation.

Each strategy remains responsible for producing the prompt it wishes to execute.

Once a prompt has been produced, a shared execution path is responsible for:

- invoking the configured language model
- validating the configured model binding
- collecting execution metrics
- constructing the resulting `StrategyOutcome`

Model binding validation is performed before execution evidence is returned.

If the responding model does not match the configured binding, execution fails immediately.

## Consequences

### Positive

- Prompt execution behavior is consistent across all prompt-backed strategies.
- Execution evidence is guaranteed to correspond to the configured model binding.
- Future execution features can be implemented in a single location.
- The execution pipeline remains provider-neutral.
- Workflow steps can reuse the same execution implementation regardless of how prompts are generated.

### Negative

- Prompt-backed strategies now share a common execution implementation, increasing coupling between those strategy types.

## Alternatives Considered

### Duplicate execution logic

Maintain separate implementations for each prompt strategy type.

Rejected because behavior would inevitably diverge as execution capabilities evolve.

### Validate model bindings after execution

Perform binding validation after constructing execution results.

Rejected because invalid execution evidence could enter the optimization pipeline before validation occurred.