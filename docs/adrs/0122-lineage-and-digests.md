# ADR 0122: Lineage and Digests

- Status: Accepted
- Date: 2026-11-10

## Context

Since 1.1, a workflow, a tool version and a benchmark dataset are lineages:
each import appends a numbered revision under a stable ID, and each revision
records the sha256 of its document's canonical JSON. Nothing is edited in
place. That is enough for one instance, whose revisions form a single line
numbered 1, 2, 3.

It is not enough once revisions travel. Pushing to a shared instance and
pulling from it (1.4's remote) must tell, for every component, whether two
instances hold the same history, whether one is ahead of the other, or
whether they have diverged. Revision numbers cannot say: two people who
each import a change on top of revision 2 both make a revision 3, with
different content and the same number. A content digest cannot say either:
a revert to revision 1's content has revision 1's digest but a different
history. And no revision records who made it, which a team needs before it
can review, approve or audit anything.

The model portfolio has the same gap. An entry records which model is
authorized, but not by whom or when.

## Decision

### A revision digest commits to a revision's whole history

Every revision gets a revision digest beside its content digest: the sha256
of its canonical identity, JSON with sorted keys and no insignificant
whitespace, encoded as UTF-8:

```json
{"content":"<content digest>","format":1,"id":"<lineage ID>","kind":"workflow","parent":"<parent revision digest or null>","version":null}
```

`kind` is `workflow`, `tool` or `benchmark`; `version` is a tool's exact
version and null otherwise; `format` names this identity, so a later one can
be told apart. Because the identity holds the parent's revision digest, a
revision digest covers the revision's whole history, as a git commit's hash
does: two instances holding a revision with the same digest hold the same
content reached by the same revisions, and a revert is a new revision whose
content digest matches an earlier one's and whose revision digest does not.

The content digest is unchanged. It is already kept in runs, evidence, tool
bindings and the editor, and stored digests are compared, never recomputed
(1.1), so its bare hex form stays. A document's references are by name or
by an ID written in the document, never by an ID one instance made, so the
same document has the same content digest on every instance, and no
reference needs to be replaced by its target's digest.

Who made a revision and when are not part of either digest, so the same
work recorded by two people is one revision.

### A revision builds on one parent

A save builds on the latest revision of its lineage, or, given `based_on`,
on the revision whose revision digest it names. The new revision is
numbered after the latest, and its parent is the revision it built on, so a
save built on an earlier revision than the latest forks. A digest that is no
revision of the lineage is refused:

```text
Revision <DIGEST> is not a revision of workflow <WORKFLOW_ID>.
```

A revision has one parent: 1.4 has no merge. Its name never implies one, so
unrelated work that happens to share a name is never connected.

### An unchanged save appends nothing

Content identical to the revision a save builds on appends nothing: the
save returns that revision and says it created none, and for a tool no
current artifact changes. This changes what 1.1 did, which appended a
duplicate revision. A duplicate recorded nothing anyone made, and once
revisions travel it would make an unchanged component look changed. A
revert, which builds on the latest revision with an earlier one's content,
is still appended, and still names the earliest revision it is identical
to.

### Every new revision records its author

An author is a name and an optional email. Who imports is the first of:

1. `AZATHOTH_AUTHOR`, as `Name <email>` or `Name`; empty counts as unset;
2. the operating system's username, without an email.

A malformed `AZATHOTH_AUTHOR` is refused rather than ignored, since a
misspelt variable silently recording someone else would be worse than
stopping:

```text
AZATHOTH_AUTHOR is '<VALUE>'; set it to "Name <email>" or "Name".
```

The service API takes the author it is opened with, `api.open(...,
author="Name <email>")`, before either, and refuses a malformed one with
`InvalidAuthorError` before anything is opened. The standard tool library
is recorded as authored by `Azathoth`: it is Azathoth's own work, the same
everywhere, so `azathoth init` never needs to know who runs it.

A configuration file for the author waits for 1.4's remote commands, which
need one anyway.

### Lineage is kept in its own table, schema version 3

A schema version only adds tables (ADR 0105), so lineage is kept beside the
revision tables rather than in new columns of them. Version 3 adds:

| Table | Holds |
| --- | --- |
| `revision_lineage` | Each revision's kind, lineage, number, revision digest, parent digest and author; unique by lineage and number, and by kind and revision digest. |
| `model_portfolio_provenance` | Each portfolio entry's content digest, author and time added. |

A table may now carry a backfill, which initializing runs once every table
is created, in the same transaction, given the names of the tables it
holds. The new tables' backfills record what an earlier database already
holds: each earlier revision's parent is the one numbered before it, each
earlier portfolio entry gets its digest, and nothing earlier has an author
or, for an entry, a time. A PostgreSQL database gains them through
`azathoth init`, which every other command asks for until it runs; an
SQLite file gains them when it is opened. Every revision appended from then
on records its lineage in the transaction that appends it, and adding or
removing a portfolio entry records or removes its provenance.

A portfolio entry is not revisioned: it has no settings for a later entry
to change. 1.4's sensitivity labels give it data-policy metadata, and with
it content worth revisioning.

### The service API and the command line show it

| Where | Shows |
| --- | --- |
| `Revision` | `revision_digest`, `parent_digest`, `parent_number`, and `author` as an `Author`, None for revisions from before 1.4 |
| `PortfolioEntry` | `content_digest`, `author` and `added_at` |
| `workflows.import_document`, `tools...`, `benchmarks...` | `based_on`; return `WorkflowImport`, `ToolImport` and `BenchmarkImport`, each with `created` |
| `workflow show`, `benchmark show` | `Revision Digest`, `Parent` and `Author` lines |
| `workflow history`, `tool history`, `benchmark history` | Each line ends `  by <name>` when the author is known |
| `workflow import`, `tool import`, `benchmark import` | `Workflow <WORKFLOW_ID> is unchanged at revision <NUMBER>.` and its kin |

Each repository says the same: `save_revision` returns a `SavedRevision`
with the revision, its lineage record and `created`, and `lineage` reads a
lineage's records. `history` keeps its meaning, the revisions of one ID, and
shows each one's parent, so no separate call lists a lineage. The heads of a
lineage that has forked come with 1.4's push and pull, which first make
forks from other instances.

The API stays provisional until 1.4.0.

## Consequences

- Push and pull can deduplicate by revision digest and tell, by walking
  parents, whether a component is ahead, behind or diverged.
- A revision says who made it, which review, approval and audit build on.
- Importing a document again that nothing changed reports it unchanged and
  writes nothing, on the command line and through the API. A script that
  counted revisions to see an import happen counts one fewer.
- The editor can save a draft on the revision it opened, so that a revision
  pulled meanwhile makes a fork rather than being silently built over.
- Every import needs an author. One that cannot be told, a malformed
  `AZATHOTH_AUTHOR` or no username at all, stops the import.
- A PostgreSQL database must be initialized again after upgrading, as for
  any new schema version.

## Alternatives Considered

### New columns on the revision tables

Lineage beside each revision row, rather than in a table of its own, would
need `ALTER TABLE` on both databases, which no schema version has done, and
a second way to migrate an SQLite file beside creating its missing tables. A
table of its own keeps the rule that a version only adds tables.

### Replace each reference with its target's digest

Hashing a workflow with the digests of the tools and child workflows it
names, Merkle style, would make its digest change when they change. Its
references are by name and by IDs its document carries, so its digest is
already the same on every instance; whether what it names has changed is
the push-time drift check's question, not its digest's.

### A new ID for every revision

Giving each revision its own generated ID, with the lineage only in its
parent pointer, would match git more closely, but every run, evidence
record, tool binding and the editor already names a revision by its lineage
ID and number. The revision digest identifies a revision across instances
without changing any of them.

### Keep appending a duplicate

1.1's duplicate revision on an unchanged import recorded no change, and
once revisions travel it would push as new work. A revert still appends.

### Read the author from git

Git's `user.name` and `user.email` are often set, but reading them means
running git or parsing its configuration, and they name who commits code,
not who runs Azathoth. `AZATHOTH_AUTHOR` says what it means.
