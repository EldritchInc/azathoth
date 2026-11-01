# ADR 0093: Budget Loops From Their Settings

- Status: Accepted; amended by ADR 0099
- Date: 2026-10-31
- Decided in: #110

## Context

`loop_workflow` (ADR 0090) is a process tool. Its implementation declares a
2-hour `timeout_seconds`, after which the engine kills it. To stop cleanly
before that, the script hard-codes a 7140-second budget, and stops each child
after 600 seconds unless the loop settings say otherwise.

The two limits agree only by hand. The script cannot see its own timeout, so
a loop that needs longer, such as a full-length novel of 18 chapters at up to
30 minutes each, meant copying the tool document, raising its timeout,
patching the budget to match, and importing the copy. A workflow's author
could choose the child timeout, but not how long the loop as a whole may run.

## Decision

The engine tells every process tool its own timeout. When an implementation
declares `timeout_seconds`, the process runs with
`AZATHOTH_TOOL_TIMEOUT_SECONDS` set to it. The rest of the environment is
inherited as before (ADR 0084).

How long a loop may run becomes a loop setting:

```text
settings.budget_seconds    optional; default 7140, or the bound below when it is shorter
```

The loop stops before its budget runs out, as it always has, and each child
is still stopped at `child_timeout_seconds` or the remaining budget,
whichever is sooner.

The budget is bounded by the tool's real timeout: the timeout less a
60-second margin, read from `AZATHOTH_TOOL_TIMEOUT_SECONDS`. The default
never exceeds that bound, so a loop tool imported with a shorter timeout
still runs without a budget. An explicit budget must be a positive number
within the bound. One outside it fails the loop before any child runs, and
says why. When the variable is absent, as when the
script is run by hand, the bound is the timeout the tool declares.

The tool's declared timeout becomes a ceiling rather than the working limit:
`loop_workflow` 1.1.0 declares 24 hours. The default budget is unchanged, so
a loop that sets no budget runs exactly as it did, and a loop that needs more
time asks for it in its settings.

The tool's input contract grows, so its definition and implementation both
become version 1.1.0, and the workflows that require it name the new version.

## Consequences

### Positive

- A long loop is configured where it is used, in its settings. No tool
  document is copied or edited.
- The budget and the timeout can no longer disagree silently. A budget the
  timeout cannot honor is refused before any work is done.
- Any process tool can now pace itself against its own timeout.

### Negative

- A loop that sets a large budget can run for up to 24 hours. The default
  stays at 7140 seconds, so a long run is always an explicit choice.
- Workflows that require `loop_workflow` 1.0.0 must name 1.1.0 to use
  budgets.
- The tool environment grows one variable. A future allow-list for process
  tool environments must keep it.

## Alternatives Considered

### Derive the default budget from the timeout

Rejected. With a 24-hour ceiling, a loop that forgot to set a budget would
be allowed to run all day.

### A timeout on each tool step

Deferred. Letting a workflow step override its tool's timeout is a larger
change to step specifications and the engine. Loops are the only tool that
needs it now, and their settings already carry the decision.

### Pass the timeout on stdin

Rejected. A tool's stdin holds its inputs, which its input schema validates.
The timeout is metadata from the engine, not an input the caller supplies.
