# ADR 0089: Substitute Models in Context-Prompt Steps

- Status: Accepted
- Date: 2026-10-26
- Decided in: #104

## Context

ADR 0051 introduced reference model substitution: from an empirical winner,
propose candidates that bind one prompt step to a strictly cheaper, authorized,
executable model.

The optimizer considered only fixed-prompt steps (`PromptStrategySpec`). It
skipped context-prompt steps, which are every step whose template reads input.
A realistic workflow, where every prompt reads something, was therefore never
offered a cheaper model, and `workflow optimize` could only rerun its baseline.

## Decision

Model substitution covers both prompt step forms:

```text
PromptStrategySpec          ──► generate_prompt_candidates
ContextPromptStrategySpec   ──► generate_context_prompt_candidates
```

The eligibility rules are unchanged: the step's selection must be a portfolio
selection, and the target must satisfy the step's requirements, be authorized,
be current, be executable, and be strictly cheaper (ADR 0051). A fixed
selection is never substituted (ADR 0059).

Substitution still changes one step at a time, in workflow step order. A
replacement keeps the step's template, inputs and output format, and receives
a new strategy identity derived from its model (ADR 0061).

Each step's strategy must match its specification. A mismatch fails
explicitly:

```text
Context-prompt workflow steps must use ContextPromptStrategy candidates.
```

## Consequences

### Positive

- Every portfolio-selected prompt step can be optimized for cost.
- Workflows built with input-reading prompts get the full optimize-and-promote
  loop.

### Negative

- Workflows with many prompt steps produce more substitution candidates per
  generation, and so cost more to optimize.

## Alternatives Considered

### Convert context-prompt steps into fixed-prompt steps for substitution

Rejected. A context prompt's template is rendered per run; it has no fixed
prompt to substitute around.
