"""Tests that pushes of one lineage at once never fork it, on a real database (ADR 0135)."""

import threading
from collections.abc import Iterator

import pytest

from azathoth.persistence import Database
from azathoth.persistence.repositories import SCHEMA_TABLES
from azathoth.remote import DivergedError, PushBundle, ReceiveReport
from tests.persistence.test_remote_reads import RecordingDatabase, Served
from tests.remote.test_closure import PARENT, PARENT_ID, parent
from tests.remote.test_receiving import bundle, local_with_history, received_by

PUSHES = 8

WAIT = 30.0


@pytest.fixture
def served(
    database: Database,
) -> Iterator[Served]:
    """Return a remote over a real database, holding the history every push builds on."""

    database.initialize(SCHEMA_TABLES)
    remote = Served(RecordingDatabase(database))
    received_by(remote, bundle(local_with_history(), PARENT))

    yield remote


def pushes() -> list[PushBundle]:
    """Return pushes of different new revisions of the parent, all built on one history."""

    bundles = []

    for index in range(PUSHES):
        local = local_with_history()
        local.workflows.save(parent(f"Counts way {index}."))
        bundles.append(bundle(local, PARENT))

    return bundles


def test_of_pushes_built_on_one_latest_revision_one_is_received_and_the_rest_diverge(
    served: Served,
) -> None:
    sent = pushes()
    start = threading.Barrier(PUSHES, timeout=WAIT)
    received: list[ReceiveReport] = []
    diverged: list[DivergedError] = []
    failures: list[BaseException] = []

    def push(
        index: int,
    ) -> None:
        try:
            start.wait()
            received.append(received_by(served, sent[index]))
        except DivergedError as refusal:
            diverged.append(refusal)
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=push, args=(index,)) for index in range(PUSHES)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(WAIT)

    history = served.workflows.lineage(PARENT_ID)

    assert failures == []
    assert (len(received), len(diverged)) == (1, PUSHES - 1)
    assert [record.number for record in history] == [1, 2, 3]
    assert [record.parent_digest for record in history[1:]] == [
        record.revision_digest for record in history[:-1]
    ]
    assert history[-1].revision_digest in {pushed.revisions[-1].revision_digest for pushed in sent}
