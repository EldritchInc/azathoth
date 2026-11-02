"""Queue worker command-line parser construction (ADR 0107)."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path

from azathoth.worker import (
    DEFAULT_EXTEND_EVERY_SECONDS,
    DEFAULT_MAX_HEARTBEAT_AGE_SECONDS,
    DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
    DEFAULT_WAIT_SECONDS,
)

WORKER_COMMAND = "worker"

WORKER_ACTION_ATTRIBUTE = "worker_action"

WORKER_RUN_ACTION = "run"

WORKER_HEALTH_ACTION = "health"

WORKER_QUEUE_URL_ATTRIBUTE = "worker_queue_url"

WORKER_RESULT_QUEUE_URL_ATTRIBUTE = "worker_result_queue_url"

WORKER_WAIT_SECONDS_ATTRIBUTE = "worker_wait_seconds"

WORKER_VISIBILITY_TIMEOUT_ATTRIBUTE = "worker_visibility_timeout_seconds"

WORKER_EXTEND_EVERY_ATTRIBUTE = "worker_extend_every_seconds"

WORKER_HEARTBEAT_FILE_ATTRIBUTE = "worker_heartbeat_file"

WORKER_MAX_AGE_ATTRIBUTE = "worker_max_age_seconds"


def add_worker_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add the queue worker's commands to the Azathoth parser."""

    worker_parser = commands.add_parser(
        WORKER_COMMAND,
        help="Run job requests from a queue.",
    )

    worker_actions = worker_parser.add_subparsers(
        dest=WORKER_ACTION_ATTRIBUTE,
    )

    run_parser = worker_actions.add_parser(
        WORKER_RUN_ACTION,
        help="Run job requests from an SQS queue, one at a time, until stopped.",
    )

    run_parser.add_argument(
        "--queue-url",
        dest=WORKER_QUEUE_URL_ATTRIBUTE,
        metavar="URL",
        required=True,
        help="The SQS queue job requests come from.",
    )

    run_parser.add_argument(
        "--result-queue-url",
        dest=WORKER_RESULT_QUEUE_URL_ATTRIBUTE,
        metavar="URL",
        default=None,
        help="A standard SQS queue to send every final job result to.",
    )

    run_parser.add_argument(
        "--wait-seconds",
        dest=WORKER_WAIT_SECONDS_ATTRIBUTE,
        metavar="SECONDS",
        type=int,
        default=DEFAULT_WAIT_SECONDS,
        help=f"How long one receive waits for a message (default {DEFAULT_WAIT_SECONDS}).",
    )

    run_parser.add_argument(
        "--visibility-timeout-seconds",
        dest=WORKER_VISIBILITY_TIMEOUT_ATTRIBUTE,
        metavar="SECONDS",
        type=int,
        default=DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
        help=(
            "How long a received message stays hidden from other workers "
            f"(default {DEFAULT_VISIBILITY_TIMEOUT_SECONDS})."
        ),
    )

    run_parser.add_argument(
        "--extend-every-seconds",
        dest=WORKER_EXTEND_EVERY_ATTRIBUTE,
        metavar="SECONDS",
        type=float,
        default=DEFAULT_EXTEND_EVERY_SECONDS,
        help=(
            "How often a running job's message is hidden again "
            f"(default {DEFAULT_EXTEND_EVERY_SECONDS})."
        ),
    )

    run_parser.add_argument(
        "--heartbeat-file",
        dest=WORKER_HEARTBEAT_FILE_ATTRIBUTE,
        metavar="PATH",
        type=Path,
        default=None,
        help="A file to touch while the worker is alive, for `azathoth worker health`.",
    )

    health_parser = worker_actions.add_parser(
        WORKER_HEALTH_ACTION,
        help="Exit 0 when a worker's heartbeat file is fresh, and 1 when it is not.",
    )

    health_parser.add_argument(
        "--heartbeat-file",
        dest=WORKER_HEARTBEAT_FILE_ATTRIBUTE,
        metavar="PATH",
        type=Path,
        required=True,
        help="The heartbeat file the worker was given.",
    )

    health_parser.add_argument(
        "--max-age-seconds",
        dest=WORKER_MAX_AGE_ATTRIBUTE,
        metavar="SECONDS",
        type=float,
        default=DEFAULT_MAX_HEARTBEAT_AGE_SECONDS,
        help=(f"How old the heartbeat may be (default {DEFAULT_MAX_HEARTBEAT_AGE_SECONDS})."),
    )


__all__ = [
    "WORKER_ACTION_ATTRIBUTE",
    "WORKER_COMMAND",
    "WORKER_EXTEND_EVERY_ATTRIBUTE",
    "WORKER_HEALTH_ACTION",
    "WORKER_HEARTBEAT_FILE_ATTRIBUTE",
    "WORKER_MAX_AGE_ATTRIBUTE",
    "WORKER_QUEUE_URL_ATTRIBUTE",
    "WORKER_RESULT_QUEUE_URL_ATTRIBUTE",
    "WORKER_RUN_ACTION",
    "WORKER_VISIBILITY_TIMEOUT_ATTRIBUTE",
    "WORKER_WAIT_SECONDS_ATTRIBUTE",
    "add_worker_parser",
]
