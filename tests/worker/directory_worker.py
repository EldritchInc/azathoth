"""Run `azathoth worker` over a directory queue, as a real process (ADR 0107).

`python -m tests.worker.directory_worker worker run ...` is the real command,
with its job queue and result queue both opened in the directory that
`AZATHOTH_TEST_QUEUE_DIRECTORY` names instead of on SQS. Nothing else
changes: the database, the runtime, the signals and the output are the
worker's own.
"""

import os
import sys
from pathlib import Path

import azathoth.cli.worker as cli_worker
from azathoth.cli import main
from tests.worker.directory_queue import DirectoryQueue

QUEUE_DIRECTORY_VARIABLE = "AZATHOTH_TEST_QUEUE_DIRECTORY"
"""The directory the worker's queues are kept in."""


def open_directory_queue(
    url: str,
) -> DirectoryQueue:
    """Open the directory queue, whatever URL the worker was given."""

    return DirectoryQueue(Path(os.environ[QUEUE_DIRECTORY_VARIABLE]))


if __name__ == "__main__":
    cli_worker.open_job_queue = open_directory_queue
    cli_worker.open_result_queue = open_directory_queue

    sys.exit(main(sys.argv[1:]))
