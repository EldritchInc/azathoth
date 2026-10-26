# ADR 0070: Compare Outcomes Beyond Exact Equality

- Status: Accepted
- Date: 2026-10-13
- Decided in: #94

## Context

Exact equality is the right test for routing labels, counts and identifiers.
It is the wrong test for most language-model output: a correct answer can
differ in case or whitespace, can be structured data whose shape matters more
than its values, or can be free text whose meaning matters more than its
wording.

Judging all of these by exact equality makes benchmarks fail correct answers,
so optimization learns from noise.

## Decision

Every `ExpectedOutcome` declares an `OutcomeComparison`:

```text
exact        type-strict JSON equality
normalized   JSON equality after normalizing every string
schema       the actual value validates against a JSON Schema
semantic     a language-model judge decides whether the meaning matches
```

Normalization is NFKC, case folding, NFKC again, then trimming and collapsing
whitespace, so `"  Duplicate_Charge\n"` matches `"duplicate_charge"`.

Comparisons belong to expected outcomes, and therefore to benchmark cases,
never to workflows. Every workflow judged against a case is held to that
case's standard, and a candidate cannot choose or relax how it is judged.
Cases in one benchmark may use different comparisons.

`OutcomeEvaluator` routes each outcome to the evaluator for its comparison.
The recorded evaluation names the evaluator that actually judged it
(`exact-match`, `normalized-match`, `json-schema`, `semantic-judge`), never the
router.

A comparison with no evaluator raises `UnsupportedComparisonError` and is
never judged by a substitute. Benchmark execution and optimization check every
case before doing any work, so unsupported work fails before it starts.

A `schema` expectation is validated as a JSON Schema when the outcome is
constructed, so an invalid schema fails at import rather than during a run.

## Consequences

### Positive

- Benchmarks can judge each output by the standard it should meet.
- Evidence names the evaluator that judged it.
- Unsupported or malformed expectations fail early.

### Negative

- Semantic judging adds provider cost and a dependency on judge models
  (ADR 0074).
- Benchmark authors must choose a comparison for every case.

## Alternatives Considered

### Declare the comparison per workflow

Rejected. A workflow could choose a lenient standard for itself, and one
workflow legitimately produces different kinds of output for different
inputs.

### Fall back to exact comparison when an evaluator is missing

Rejected. A case would be judged by a standard its author did not declare.
