"""What a remote sends for a pull: the documents asked for, and what they need (ADR 0124).

A pull is a closure, gathered at the remote. A benchmark any revision of
which is restricted comes only to a pull that asks for restricted data;
otherwise it is withheld and named, and the rest still comes. The revisions
the client already holds are left out, and the content the bundle's
benchmarks hold is named, for the client to fetch what it lacks.
"""

from azathoth.evaluation import BenchmarkRepository
from azathoth.remote.closure import closure
from azathoth.remote.records import PullRequest, PullResponse, PushBundle
from azathoth.revisions import Lineage, RevisionKind
from azathoth.sensitivity import Sensitivity
from azathoth.tools import ToolRepository
from azathoth.workflows import WorkflowRepository


def pull(
    request: PullRequest,
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
) -> PullResponse:
    """Return the bundle a pull asks for, without restricted benchmarks unless it asks for them."""

    gathered = closure(request.roots, workflows=workflows, tools=tools, benchmarks=benchmarks)
    withheld: list[Lineage] = []

    if not request.include_restricted:
        for record in gathered.revisions:
            if (
                record.lineage.kind is RevisionKind.BENCHMARK
                and record.sensitivity is Sensitivity.RESTRICTED
                and record.lineage not in withheld
            ):
                withheld.append(record.lineage)

    if withheld:
        gathered = closure(
            (root for root in request.roots if root not in withheld),
            workflows=workflows,
            tools=tools,
            benchmarks=benchmarks,
        )

    held = set(request.held)

    return PullResponse(
        bundle=PushBundle(
            revisions=tuple(
                record for record in gathered.revisions if record.revision_digest not in held
            ),
            content=gathered.content,
        ),
        withheld=tuple(withheld),
        unresolved=gathered.unresolved,
    )


__all__ = [
    "pull",
]
