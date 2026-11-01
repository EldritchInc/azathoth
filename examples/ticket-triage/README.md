# Ticket Triage Example

`triage-ticket.json` triages one customer support ticket. It classifies the
ticket, has the right specialist draft a reply, checks the reply against
support policy, and decides whether a person must look at it before it is
sent.

```text
classify ──► billing specialist      (runs when the category is billing)
         ├─► technical specialist    (runs when the category is technical)
         ├─► account specialist      (runs when the category is account)
         └─► generalist              (runs for anything else)
                    │
                    ▼
             policy check ──► finalize
```

| Document | ID |
| --- | --- |
| `workflows/triage-ticket.json` | `f1000000-0000-4000-8000-000000000030` |
| `workflows/classify-ticket.json` | `f1000000-0000-4000-8000-000000000010` |
| `workflows/classify-ticket-escalating.json` | `f1000000-0000-4000-8000-000000000070` |
| `tools/finalize-triage.json` | `f1000000-0000-4000-8000-000000000001` |
| `benchmarks/classify-ticket.json` | `f1000000-0000-4000-8000-000000000050` |
| `benchmarks/triage-ticket.json` | `f1000000-0000-4000-8000-000000000060` |

## Routing With Conditions

The four specialists share one dependency layer, and each is conditioned on
the classifier's category, so exactly one runs. The generalist's three
`not_equal` conditions make it the catch-all: a category the classifier
invents still gets a reply.

Every specialist produces `draft`, and the policy check reads it by name. The
skipped specialists produce nothing, so the one that ran is the one read (ADR
0080).

## Running It

With a provider configured and models authorized (see the CLI README):

```bash
azathoth tool import examples/ticket-triage/tools/finalize-triage.json

azathoth workflow import examples/ticket-triage/workflows/classify-ticket.json
azathoth workflow import examples/ticket-triage/workflows/triage-ticket.json

azathoth workflow run f1000000-0000-4000-8000-000000000030 \
    --input '{"subject": "Charged twice", "body": "My card was charged twice for the March invoice.", "customer_tier": "standard"}' \
    --output result
```

The result is the triage record:

```json
{
  "category": "billing",
  "urgency": "normal",
  "summary": "...",
  "reply": "...",
  "approved": true,
  "problems": [],
  "needs_human": false
}
```

`needs_human` is true when the policy check did not approve the reply, or
when the ticket is urgent, even if it did.

## Benchmarks and a Cheaper Classifier

`classify-ticket.json` is the triage workflow's classifier on its own. Both
workflows use the same classifier strategy, so a better classifier found for
one is the same strategy in the other.

Its benchmark has six exact cases, so it needs no judge. Classifying a ticket
is a small task, which makes it a good candidate for a cheaper model:

```bash
azathoth benchmark import examples/ticket-triage/benchmarks/classify-ticket.json

azathoth workflow optimize f1000000-0000-4000-8000-000000000010 \
    --benchmark f1000000-0000-4000-8000-000000000050 \
    --target-latency 5 \
    --target-cost 0.001
```

The first generation measures the classifier as configured, and the
optimizer offers it each strictly cheaper authorized model that meets its
requirements (ADR 0089). The final evaluation runs every candidate against
the benchmark (ADR 0091), and the report names the winner on quality,
latency and cost. It does not promote the winner: deploying it is a
separate, deliberate step.

## Escalating When Unsure

A cheaper classifier is cheaper on every ticket and wrong on some.
`classify-ticket-escalating.json` keeps the cheap model for the tickets it is
sure of, and pays for a stronger one only on the rest (ADR 0098):

```text
classify cheaply ──► confidence < 0.8? ──► escalate to a stronger model
        │                                           │
        └──────────────── category ◄────────────────┘
```

The cheap classifier asks for the same category, urgency and summary as
`classify-ticket.json`, and for how sure it is, from 0 to 1. It declares that
output as its confidence:

```json
"outputs": [..., {"name": "confidence", "path": ["confidence"]}],
"confidence": "confidence"
```

Its model must cost at most $0.50 per million input tokens and $1.50 per
million output tokens, with known pricing. The escalation step has no price
limit, so it runs on the first authorized model in the portfolio: put the
strongest model you want to escalate to first.

The escalation step is conditioned on the classifier's confidence:

```json
"conditions": [{"source": {"producer_step_id": "f1000000-0000-4000-8000-000000000071", "name": "confidence"}, "operator": "less_than", "expected": 0.8}]
```

It is shown the ticket and the cheap model's guess, and produces the same
`category`, `urgency` and `summary`. It is declared *first* in the workflow's
steps, so the workflow's result, `category` read by name, is the escalation
step's whenever it ran and the classifier's when it was skipped (ADR 0080).

```bash
azathoth workflow import examples/ticket-triage/workflows/classify-ticket-escalating.json

azathoth workflow run f1000000-0000-4000-8000-000000000070 \
    --input '{"subject": "Downgrade my plan", "body": "How do I move from Pro to the Starter plan at renewal?", "customer_tier": "standard"}' \
    --output text
```

The text report names the classifier's confidence beside its model. A ticket
the classifier is sure of shows the escalation step as `skipped`; one it is
unsure of shows it `executed`, on the stronger model.

A step whose confidence is not a number from 0 to 1 fails that attempt and
is retried, so a model that forgets to say how sure it is never passes for
sure or unsure.

Whether escalating pays off is an empirical question, and the classifier's
benchmark answers it. Compare the escalating classifier with the plain one on
quality, latency and cost:

```bash
azathoth benchmark compare f1000000-0000-4000-8000-000000000050 \
    --workflow f1000000-0000-4000-8000-000000000010 \
    --workflow f1000000-0000-4000-8000-000000000070 \
    --target-latency 5 \
    --target-cost 0.001
```

The threshold, 0.8, is the condition's `expected` value. A model's
confidence in itself is not calibrated: a confidently wrong answer is not
escalated, and too high a threshold escalates nearly everything. Change the
threshold, import the workflow again, and compare again.

## The Triage Benchmark

The triage benchmark has three semantic cases, judged on the reply and the
routing, and one schema case requiring a complete, valid triage record.
Semantic cases need a judge:

```bash
azathoth judge add <MODEL_IDENTIFIER>
azathoth benchmark import examples/ticket-triage/benchmarks/triage-ticket.json
```
