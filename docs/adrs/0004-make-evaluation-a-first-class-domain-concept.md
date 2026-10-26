# ADR 0004: Make Evaluation a First-Class Domain Concept

- Status: Accepted
- Date: 2026-07-30

## Decision

Introduce EvaluationResult and Evaluator abstractions instead of embedding
evaluation logic directly into optimization code.

## Rationale

Execution and evaluation are different concerns.

The same strategy may be evaluated using:

- exact matching
- LLM judges
- human review
- classifier confidence
- business rules

Treating evaluation as a domain concept allows multiple evaluation
implementations while preserving identical execution behavior.

## Consequences

- evaluation is pluggable
- evaluation is reproducible
- evaluation can evolve independently
- optimization algorithms consume EvaluationResult rather than evaluator implementations
