# Azathoth

> Empirical optimization for context-aware AI workflows.

Azathoth is an open-source engine for building LLM workflows by composing
them rather than coding them, and then improving them with measured
evidence rather than intuition.

You describe a workflow as a JSON document:

- prompt steps that state model requirements instead of naming models;
- tool steps;
- child workflows and loops;
- the dependencies, conditions and failure policies between them.

Azathoth runs it and benchmarks it. It searches for the models that pass your
benchmark at the latency and cost you target. It deploys only what you
deliberately promote.

```text
define ──► run ──► benchmark ──► optimize ──► promote ──► invoke production
```

## Workflows Are Composed, Not Coded

Most LLM workflows are programs: prompts in source files, models as
constants, control flow as code. Every change, whether a new model, a
reworded prompt or an extra review step, goes through engineering.

Azathoth makes building a workflow a composition activity. That moves LLM
workflows out of engineering and into the hands of the teams who run and own
them:

- **platform and DevOps teams** operate workflows like infrastructure: versioned
  revisions, explicit promotion, production state and an audit trail of
  every invocation;
- **domain experts** define what a good answer is, as benchmark cases, exact
  or judged by a model, and Azathoth measures every candidate against them;
- **engineers** write **tools**: small, versioned, tested units of
  deterministic work that workflows compose.

Writing code should be for tools, not for LLM workflows.

## Quick Look

Install it in a virtual environment. The [install guide](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md)
explains why a venv, and gives the Windows commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install azathoth-ai
azathoth --version
```

From a clone of this repository, run a workflow built from two tools. It
needs no model and no API key:

```bash
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result
```

It prints `8`. To go from there to a model-backed workflow that is
benchmarked, optimized, promoted and invoked in production, follow
[Getting Started](https://github.com/EldritchInc/azathoth/blob/main/docs/getting-started.md).

## Documentation

| Guide | What it covers |
| --- | --- |
| [Installing Azathoth](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md) | Python, a venv, `pip install`, checking it works, on macOS and Windows |
| [Connecting OpenRouter](https://github.com/EldritchInc/azathoth/blob/main/docs/openrouter.md) | An API key, finding and authorizing models, adding judges |
| [Getting Started](https://github.com/EldritchInc/azathoth/blob/main/docs/getting-started.md) | One workflow from import to production |
| [Examples Tour](https://github.com/EldritchInc/azathoth/blob/main/docs/examples.md) | Every example, from a word count to a novel |
| [Concepts](https://github.com/EldritchInc/azathoth/blob/main/docs/concepts.md) | How Azathoth is put together, and why |
| [CLI Reference](https://github.com/EldritchInc/azathoth/blob/main/src/azathoth/cli/README.md) | Every command, its options and its output |
| [Architecture Decisions](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/README.md) | The ADRs behind each boundary |
| [Contributing](https://github.com/EldritchInc/azathoth/blob/main/CONTRIBUTING.md) | Working on Azathoth itself |
| [Releasing](https://github.com/EldritchInc/azathoth/blob/main/RELEASING.md) | How a release is validated and published |

## Examples

The [examples](https://github.com/EldritchInc/azathoth/tree/main/examples)
are complete, importable workflows, each with its benchmarks and end-to-end
tests:

- **word count**: tools, redundancy, and benchmark cases made from corrected
  runs;
- **classify sentiment**: the whole lifecycle in one step;
- **child workflow** and **countdown loop**: composing workflows;
- **ticket triage**: conditional routing to specialists, and a cheaper
  classifier found by the optimizer;
- **workflow writer**: a workflow that writes workflows and validates them;
- **code review**: three concurrent reviewers, merged by code rather than a
  model;
- **novel**: nested loops that plan, draft, edit and revise a book.

## What Azathoth Does

- **Composes workflows** from prompt, tool and child-workflow steps. Steps can
  depend on each other, pass values by name, run conditionally, retry, and
  fail in a controlled way.
- **Separates intent from models.** Steps state requirements, and Azathoth
  chooses from the models you have authorized among those OpenRouter
  currently offers.
- **Records everything**: every run, step, attempt, prompt, reply, token and
  cost, as durable evidence.
- **Benchmarks** workflows with exact, normalized, schema and model-judged
  semantic cases.
- **Optimizes** by trying strictly cheaper authorized models, step by step,
  and ranking candidates on quality, reliability, latency and cost. The
  report shows which model each step of the winner used.
- **Promotes deliberately.** Production runs only what was explicitly
  promoted, on exact models, with a revision history and an invocation log.
  Optimizing never deploys anything by itself.

Azathoth is also a typed Python library. The
[package READMEs](https://github.com/EldritchInc/azathoth/blob/main/docs/concepts.md#package-guide)
document each subsystem.

## Design Principles

> **Persist what should happen. Compose what can execute. Record what
> actually happened. Change production deliberately.**

- **Evidence over intuition.** A candidate is better only once it has been
  measured as better.
- **Composition over code.** Workflows are documents; code lives in tools.
- **Provider independence.** Workflows describe model requirements; providers
  are attached at run time.
- **Explicit production authority.** Production is what you promoted, not the
  latest optimizer winner or the cheapest model.
- **Immutable records.** Configuration, runs, evaluations and deployments are
  never rewritten.

[Concepts](https://github.com/EldritchInc/azathoth/blob/main/docs/concepts.md)
explains each of these in depth.

## Project Status

Azathoth 1.0 requires Python 3.11 or newer and uses OpenRouter as its model
provider. The guides cover macOS and Windows; the macOS commands also work on
Linux.

## Support the Project

If you find Azathoth useful and would like to support its continued
development, you can become a patron:

**❤️ Patreon:** https://patreon.com/ErisDiscordiaM

Your support funds ongoing development, experiments, documentation, testing
and long-term maintenance.

## License

Azathoth is licensed under the
[MIT License](https://github.com/EldritchInc/azathoth/blob/main/LICENSE).
