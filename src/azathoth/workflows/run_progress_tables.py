"""The tables that record a run while it executes, so it can be resumed (ADR 0105).

They are schema version 2. Each holds what a finished `WorkflowRun` cannot:

- `run_journal`: the append-only journal of a run that has started, numbered
  from 1 within the run.
- `run_leases`: the process that holds a run while it executes, until when.
- `run_children`: the runs a step of another run started, keyed by the child.
"""

from azathoth.persistence import Table

RUN_JOURNAL_TABLES = (
    Table(
        name="run_journal",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS run_journal (
                sequence {sequence},
                run_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                workflow_id TEXT NOT NULL,
                invocation_id TEXT,
                event_type TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (run_id, position)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                run_journal_invocation_id_position
            ON run_journal (
                invocation_id,
                position
            )
            """,
        ),
    ),
)
"""The table every run's journal is kept in, one entry per row."""

RUN_LEASE_TABLES = (
    Table(
        name="run_leases",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS run_leases (
                run_id TEXT NOT NULL PRIMARY KEY,
                holder TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """,
        ),
    ),
)
"""The table of the leases on runs that are executing, one per run."""

RUN_CHILD_TABLES = (
    Table(
        name="run_children",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS run_children (
                sequence {sequence},
                child_run_id TEXT NOT NULL UNIQUE,
                child_workflow_id TEXT NOT NULL,
                child_invocation_id TEXT,
                parent_run_id TEXT NOT NULL,
                parent_step_id TEXT NOT NULL,
                parent_attempt INTEGER NOT NULL,
                root_run_id TEXT NOT NULL,
                depth INTEGER NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                run_children_parent_run_id_sequence
            ON run_children (
                parent_run_id,
                sequence
            )
            """,
        ),
    ),
)
"""The table indexing each child run under the run whose step started it."""

RUN_PROGRESS_TABLES = (
    *RUN_JOURNAL_TABLES,
    *RUN_LEASE_TABLES,
    *RUN_CHILD_TABLES,
)
"""Every table schema version 2 adds, in the order `initialize` creates them."""


__all__ = [
    "RUN_CHILD_TABLES",
    "RUN_JOURNAL_TABLES",
    "RUN_LEASE_TABLES",
    "RUN_PROGRESS_TABLES",
]
