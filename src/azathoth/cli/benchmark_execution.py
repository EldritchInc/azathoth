"""Executing configured workflows against benchmarks, from the command line.

The calls live in the service API (ADR 0130), so `benchmark run` and
`benchmark compare` execute a benchmark as `benchmarks.run` and
`benchmarks.compare` do; they are named here too, where the command line
has always found them.
"""

from azathoth.api.benchmark_execution import (
    case_runner,
    compare_configured_benchmarks,
    execute_configured_benchmark,
    judged_sensitivity,
)

__all__ = [
    "case_runner",
    "compare_configured_benchmarks",
    "execute_configured_benchmark",
    "judged_sensitivity",
]
