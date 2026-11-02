"""Tests for the worker's heartbeat file and its health check (ADR 0107)."""

import os
import time
from pathlib import Path

import pytest

from azathoth.worker import (
    DEFAULT_MAX_HEARTBEAT_AGE_SECONDS,
    HeartbeatError,
    HeartbeatFile,
    check_heartbeat,
)


def test_a_heartbeat_creates_its_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "heartbeat"

    HeartbeatFile(path).beat()

    assert path.exists()


def test_every_heartbeat_moves_the_files_time_forward(
    tmp_path: Path,
) -> None:
    path = tmp_path / "heartbeat"
    heartbeat = HeartbeatFile(path)
    heartbeat.beat()
    os.utime(path, (1_000_000, 1_000_000))

    heartbeat.beat()

    assert path.stat().st_mtime > time.time() - 60


def test_a_heartbeat_that_cannot_be_written_says_where_and_why(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "heartbeat"

    with pytest.raises(HeartbeatError) as raised:
        HeartbeatFile(path).beat()

    assert str(raised.value) == (
        f"Cannot write the heartbeat file {path}: No such file or directory."
    )


def test_a_worker_is_unhealthy_until_its_first_heartbeat(
    tmp_path: Path,
) -> None:
    path = tmp_path / "heartbeat"

    health = check_heartbeat(path, max_age_seconds=90)

    assert not health.healthy
    assert health.age_seconds is None
    assert health.message == (
        f"No heartbeat at {path}; the worker has not started, or cannot write it."
    )


def test_a_fresh_heartbeat_is_healthy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "heartbeat"
    HeartbeatFile(path).beat()
    os.utime(path, (1_000_000, 1_000_000))

    health = check_heartbeat(path, max_age_seconds=90, now=1_000_012.4)

    assert health.healthy
    assert health.age_seconds == pytest.approx(12.4)
    assert health.message == f"The last heartbeat at {path} is 12 seconds old."


def test_a_stale_heartbeat_is_unhealthy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "heartbeat"
    HeartbeatFile(path).beat()
    os.utime(path, (1_000_000, 1_000_000))

    health = check_heartbeat(path, max_age_seconds=90, now=1_000_091)

    assert not health.healthy
    assert health.message == (
        f"The last heartbeat at {path} is 91 seconds old, older than 90 seconds."
    )


def test_a_heartbeat_from_the_future_is_zero_seconds_old(
    tmp_path: Path,
) -> None:
    path = tmp_path / "heartbeat"
    HeartbeatFile(path).beat()
    os.utime(path, (1_000_010, 1_000_010))

    health = check_heartbeat(path, max_age_seconds=90, now=1_000_000)

    assert health.healthy
    assert health.age_seconds == 0


def test_a_heartbeat_is_healthy_for_ninety_seconds_by_default() -> None:
    assert DEFAULT_MAX_HEARTBEAT_AGE_SECONDS == 90
