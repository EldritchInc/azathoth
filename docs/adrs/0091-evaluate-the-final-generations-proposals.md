# ADR 0091: Evaluate the Final Generation's Proposals

- Status: Accepted
- Date: 2026-10-31
- Decided in: #108

## Context

An optimization session alternates two steps. An experiment runs the current
candidate population against the benchmark, and the optimizer proposes the
next population from that experiment's winner:

```text
generation 1   experiment(population 0)  ->  propose population 1
generation 2   experiment(population 1)  ->  propose population 2
...
generation N   experiment(population N-1) -> propose population N
```

Population N is recorded in the session but never run. With the default of
`--generations 1`, the session measures the configured workflow, proposes
cheaper model substitutions, and stops. Its winner is always the configured
workflow, so the default compares no models.

The 1.0 documentation worked around this by teaching `--generations 2`, and
a docs test required every concrete optimize command to pass
`--generations`. Every session still discarded its last proposals: running
them costs one more experiment, but proposing them and never measuring them
gives nothing for the work.

## Decision

After the last generation, the session runner runs one more experiment, the
final evaluation, over the last generation's population. Like every
generation's experiment, it runs the whole population, including the
candidates carried forward, against every benchmark case.

The final evaluation runs only when the last population holds a candidate
whose signature the last experiment did not evaluate. When the optimizer
proposed nothing new, the last experiment already measured the final
population, and running it again would repeat the same work.

The session records the final evaluation separately from its generations.
A generation is an experiment plus the population it led to; the final
evaluation leads to no population. The session's winning experiment is the
final evaluation when there is one, and the last generation's experiment
otherwise. Its winner is the session's winner.

`--generations N` therefore means N rounds of proposals, each of them
measured. The default of 1 measures the configured workflow, proposes
cheaper substitutes, and measures them.

The final evaluation is recorded like any other experiment, so it appears in
`workflow experiments` and `experiment show`.

## Consequences

### Positive

- The default optimize command compares models.
- No session ends on proposals it never measured.
- Documentation no longer needs to explain why the default does nothing
  useful, and the docs test that required `--generations` is removed.
- The session's winner comes from one recorded experiment, which a later
  command can promote by ID.

### Negative

- `--generations N` now runs up to N + 1 experiments. A script that passed
  `--generations 2` to work around the 1.0 behavior now runs one more round
  than it needs, and pays for it.
- A session's experiments no longer map one-to-one onto its generations.
  Readers of a session must look at the final evaluation as well as the
  generations.

## Alternatives Considered

### Make 2 the default

Rejected. The default would compare models, but every session would still
end on a population it never measured, and the meaning of N would stay
surprising.

### Redefine N as rounds of substitution

Rejected as a separate option, because it needs the same final experiment to
measure the last round. This decision is that redefinition, with the
experiment made explicit and skipped when it would add nothing.

### Always run the final evaluation

Rejected. When the optimizer proposes nothing new, the final population is
the one just measured, and rerunning it costs a full benchmark pass for no
new evidence.
