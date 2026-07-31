# ADR 0007: Separate experiment execution from strategy ranking

## Status

Accepted

## Context

Azathoth must both collect evidence about candidate strategies and interpret
that evidence to select preferred candidates.

Combining experiment execution and ranking would couple the process of
generating evidence to one particular selection policy.

Different applications may eventually rank candidates using different
objectives, including:

- quality;
- pass rate;
- cost;
- latency;
- reliability;
- complexity;
- or multi-objective tradeoffs.

## Decision

Separate these responsibilities.

`ExperimentRunner` executes every candidate strategy against every supplied
example and produces one `StrategyScorecard` per candidate.

`StrategyRanker` consumes completed scorecards and returns a deterministic
`StrategyRanking`.

The initial ranking policy prefers:

1. higher pass rate;
2. higher mean evaluation score;
3. larger evidence sets;
4. deterministic strategy identity ordering.

## Consequences

Benefits:

- experiments can be reused with different ranking policies;
- evidence collection remains independent of optimization objectives;
- ranking behavior is deterministic and directly testable;
- future cost- and latency-aware rankers can be added without changing
  experiment execution;
- callers can inspect scorecards without accepting a selected winner.

Costs:

- callers coordinate two services instead of one;
- the initial ranking policy is intentionally simple;
- future ranking policies will require explicit configuration or new
  implementations.