# ADR 0086: Add Benchmark Cases Only Deliberately, From Recorded Runs

- Status: Accepted
- Date: 2026-10-26
- Decided in: #102

## Context

Recorded runs (ADR 0068) and feedback with corrected outputs are the best
source of new benchmark cases: real inputs, with a known right answer. Turning
them into cases automatically, however, would let every judgment silently
change the standard that every future candidate is held to.

Benchmarks are evidence infrastructure. A change to one must be a deliberate,
recorded act.

## Decision

An operator adds a case from a recorded run explicitly:

```bash
azathoth benchmark add-case <BENCHMARK_ID> --from-run <RUN_ID> --comparison <COMPARISON>
azathoth benchmark add-case <BENCHMARK_ID> --from-run <RUN_ID> --comparison <COMPARISON> --expected <JSON>
```

The case's input is the run's `workflow.input.received` input, which a run
must have received exactly once.

The expected value comes from `--expected`, or else from the latest bad
feedback on that run that carries a corrected output. Good feedback never
supplies an expected value: a run judged good may still be wrong in ways
nobody noticed. Without either source, the command fails:

```text
Run <RUN_ID> has no corrected output; pass --expected.
```

Adding a case appends a new benchmark revision (ADR 0076). The new case goes
after every existing case, and its metadata names the source run, and the
feedback, if any. The dataset's declared `version` is unchanged, because the
version is the author's declaration and the revision number is the lineage.

An exact duplicate (JSON-equal input, same comparison, JSON-equal expected
value) is rejected. Separate cases with the same input and different expected
values are allowed, so several acceptable answers can be recorded; per-case
alternatives are deferred until after 1.0.

Any workflow can run against any benchmark, so adding a case does not check
which workflow produced the run. Semantic cases need no judges when added.

## Consequences

### Positive

- Real failures become regression cases with one command.
- Every change to a benchmark is a recorded revision with a named source.
- Feedback never moves the standard on its own.

### Negative

- Operators must remember to turn corrections into cases.
- With exact comparisons, a workflow cannot pass two cases that share an input
  but expect different values.

## Alternatives Considered

### Add a case automatically for every bad feedback

Rejected. Judgments would silently change benchmarks.

### Let good feedback supply the run's output as expected

Rejected. "Nobody objected" is not a correct answer.
