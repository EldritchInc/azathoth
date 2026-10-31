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

The triage benchmark has three semantic cases, judged on the reply and the
routing, and one schema case requiring a complete, valid triage record.
Semantic cases need a judge:

```bash
azathoth judge add <MODEL_IDENTIFIER>
azathoth benchmark import examples/ticket-triage/benchmarks/triage-ticket.json
```
