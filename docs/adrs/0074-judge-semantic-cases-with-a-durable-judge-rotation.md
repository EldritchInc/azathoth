# ADR 0074: Judge Semantic Cases With a Durable Judge Rotation

- Status: Accepted
- Date: 2026-10-23
- Decided in: #97

## Context

ADR 0070 introduced the `semantic` comparison, which needs language-model
judges. Judges vary, so how they are assigned decides whether rankings are
fair. If two candidates answering the same case met different judges, judge
variance would leak into the comparison between candidates.

Judges also see benchmark data, and they can fail.

## Decision

Judges come from a durable, ordered `JudgeRotation` of `JudgeEntry` values,
each identified as `<provider>/<model>`, persisted through
`JudgeRotationRepository` (`InMemoryJudgeRotationRepository` and
`SQLiteJudgeRotationRepository`).

The CLI manages it with `judge add`, `judge list` and `judge remove`. A judge
must be both currently available and authorized in the model portfolio
(ADR 0058), because judges see benchmark data.

Judges are assigned per expectation, never per candidate or per call:

```text
first judge = sha256(canonical JSON of description, value, comparison)
              mod judge count
```

The rest follow in rotation order, wrapping around. Every candidate judged
against the same case therefore meets the same judge first.

A judge that raises, or replies without a usable verdict, is followed by the
next judge. The first usable verdict decides. Verdicts are binary, `pass` or
`fail`, with a one-sentence reason, so semantic results count alongside every
other comparison.

When every judge fails, judging raises `SemanticJudgingError`, and the command
running the benchmark stops. A judging failure is Azathoth's infrastructure
failure, never the candidate's, and is never recorded as a failed case.

Semantic cases need no judges at import time. Judges are checked when a
benchmark is run, compared or optimized against:

```text
Benchmark case <CASE_ID> uses comparison 'semantic', but no judges are configured.
```

## Consequences

### Positive

- Candidates are compared under the same judge.
- Assignment is reproducible across processes and platforms.
- A judge outage cannot corrupt a ranking.

### Negative

- Adding or removing a judge reassigns cases.
- A single judge's bias applies consistently to every candidate on its cases.

## Alternatives Considered

### Pick a judge at random per call

Rejected. Judge variance would decide rankings.

### Record a judging failure as a failed case

Rejected. Candidates would be penalized for Azathoth's outages.
