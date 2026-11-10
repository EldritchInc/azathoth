# Sensitivity

`azathoth.sensitivity` labels how sensitive data is, and decides which models
may receive it (ADR 0123).

```python
from azathoth.sensitivity import (
    DataPolicy,
    PolicyAnswer,
    Sensitivity,
    may_receive,
    most_sensitive,
    require_no_lower,
    restricted_refusal,
)
```

## Labels

A `Sensitivity` is `public`, `internal` or `restricted`. Data that names no
label is `internal` (`DEFAULT_SENSITIVITY`), and `effective_sensitivity`
reads an absent label that way.

Labels are ordered by `rank`, from public to restricted, never by their
names: as text, `internal` sorts before `public`. `most_sensitive(labels)`
returns the most sensitive of some labels, which is the label of anything
derived from them. `stored_sensitivity(label)` is a label as data keeps it:
`None` for internal, so data that is internal serializes, and digests, as it
did before labels existed.

A label is never lowered by deriving data. `require_no_lower(label, floor,
source=..., derived=...)` refuses a label below what the data came from:

```text
Run <RUN_ID> is restricted; a case made from it cannot be internal.
```

## Data Policies

A `DataPolicy` says whether a model's provider retains the data it is sent,
`retains_data`, and whether it trains on it, `trains_on_data`. Each is a
`PolicyAnswer`: `yes`, `no` or `unknown`. Whoever authorizes the model
declares it; Azathoth never assumes a provider's terms, so both are unknown
until declared (`UNKNOWN_DATA_POLICY`). A policy that answers `no` to both is
private (`PRIVATE_DATA_POLICY`). A model's policy is kept on its portfolio
entry, declared with `azathoth model authorize` or `azathoth model policy`
(see the CLI's "Declare a Model's Data Policy").

`may_receive(policy, label)` decides whether a model may be sent data: any
model may receive public and internal data, and only a private one may
receive restricted data. A model outside the portfolio has no policy, so it
may not.

`restricted_refusal(model, policy)` says why a model may not receive
restricted data, naming each answer that forbids it, and
`RESTRICTED_REFUSAL_HINT` what to do about it:

```text
openrouter/example/frontier cannot receive restricted input: its portfolio entry does not say whether its provider retains data, and does not say whether it trains on data.
If its provider neither retains nor trains on data, declare that with `azathoth model policy openrouter/example/frontier --no-retention --no-training`; otherwise choose a model that may receive restricted input.
```

Labels guard Azathoth's own paths out, to models, child workflows, push,
pull and telemetry, against mistakes. They are not a boundary against a tool
written to carry data elsewhere: tools gain data policies after 1.4.

## Where Labels Are Enforced

In 1.4.0a4 a restricted run's data may leave Azathoth through models, and
every model path is guarded:

| Path | Guard |
| --- | --- |
| A context prompt step | `ContextPromptStrategy` refuses to send to a model that may not receive the running step's label, `active_step_lineage().sensitivity` |
| Choosing a step's model | Candidate generation tries the models that may receive the run's label first; production prefers such a model among the primary and its approved substitutes |
| Semantic judges | `outcome_evaluator(semantic=True, sensitivity=...)` refuses a judge that may not receive the label of the cases it judges |
| Optimization | Substitution offers a restricted context prompt only private models |
| Child workflows | A child inherits its parent's label through lineage, so its own prompts are guarded the same way |

A fixed prompt holds only its own text, so it is not guarded. Tools are not
guarded in 1.4.
