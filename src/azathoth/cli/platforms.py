"""Where Azathoth tests serving a remote and running its queue worker (ADR 0142).

A remote is served, and the queue worker run, from Linux or macOS, where
both are tested. Either still runs on Windows, at its operator's own risk,
saying so once as it starts. Reaching a remote is tested on every platform.
"""

import sys
from typing import Final

SERVING_ON_WINDOWS_WARNING: Final = (
    "Serving a remote on Windows is untested and at your own risk; Azathoth tests "
    "serving on Linux and macOS (ADR 0142)."
)
"""What `azathoth remote serve` says first on Windows."""

WORKER_ON_WINDOWS_WARNING: Final = (
    "Running the queue worker on Windows is untested and at your own risk; Azathoth "
    "tests it on Linux and macOS (ADR 0142)."
)
"""What `azathoth worker run` says first on Windows, once its settings are valid."""


def on_windows() -> bool:
    """Return whether this Python runs on Windows."""

    return sys.platform == "win32"


__all__ = [
    "SERVING_ON_WINDOWS_WARNING",
    "WORKER_ON_WINDOWS_WARNING",
    "on_windows",
]
