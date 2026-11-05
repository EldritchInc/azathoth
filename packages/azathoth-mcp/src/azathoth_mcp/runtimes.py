"""The runtime tool calls run on, composed again only when production changes (ADR 0111).

Composing a runtime reads every workflow, model and tool from the database,
and discovers provider models, which can take a while. A long-running server
keeps the runtime it composed, and composes a new one only when a call finds
that the workflow it invokes has a different active production state than
the kept runtime holds, as after a workflow is promoted again.
"""

import threading
from collections.abc import Callable
from uuid import UUID

from azathoth.runtime import AzathothRuntime
from azathoth.workflows import WorkflowProductionState


class RuntimeProvider:
    """Keep one runtime, and compose it again when production has moved on.

    It is called from worker threads, as the job service composes runtimes
    there, so one lock keeps two calls from composing at once.
    """

    def __init__(
        self,
        load: Callable[[], AzathothRuntime],
    ) -> None:
        self._load = load
        self._runtime: AzathothRuntime | None = None
        self._lock = threading.Lock()

    def runtime_for(
        self,
        workflow_id: UUID,
        state: WorkflowProductionState | None,
    ) -> AzathothRuntime:
        """Return a runtime whose active state for one workflow is the one given.

        The kept runtime is returned when it holds that state, and a new one
        is composed, and kept, when it holds another or none has been composed.
        """

        with self._lock:
            if self._runtime is None or self._runtime.production_state(workflow_id) != state:
                self._runtime = self._load()

            return self._runtime


__all__ = [
    "RuntimeProvider",
]
