"""What a remote tells a client it holds: lineage heads, its portfolio, and missing credentials.

These answer a client's status (ADR 0125). Each reads only: a head names
revisions by digest, the portfolio names models and their declared data
policies, and the credential check says which names are unset, never what
any variable holds.
"""

from collections.abc import Iterator, Mapping

from azathoth.evaluation import BenchmarkRepository
from azathoth.providers import ModelPortfolioRepository
from azathoth.remote.closure import ancestry, lineage_records
from azathoth.remote.records import (
    CredentialsRequest,
    CredentialsResponse,
    Head,
    HeadsRequest,
    HeadsResponse,
    PortfolioRecord,
    PortfolioResponse,
)
from azathoth.revisions import Lineage, RevisionKind, content_digest
from azathoth.tools import ToolRepository
from azathoth.tools.environment import grant_matches
from azathoth.workflows import WorkflowProductionStateRepository, WorkflowRepository


def held_lineages(
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
) -> Iterator[Lineage]:
    """Yield every lineage an instance holds: workflows, then tool versions, then benchmarks."""

    for specification in workflows.specifications():
        yield Lineage(kind=RevisionKind.WORKFLOW, id=specification.metadata.id)

    for definition in tools.definitions():
        yield Lineage(kind=RevisionKind.TOOL, id=definition.id, version=definition.version)

    for dataset in benchmarks.datasets():
        yield Lineage(kind=RevisionKind.BENCHMARK, id=dataset.id)


def production_digest(
    lineage: Lineage,
    *,
    workflows: WorkflowRepository,
    production_states: WorkflowProductionStateRepository,
) -> str | None:
    """Return the digest of the workflow revision in production, or None where none is.

    A state promoted before revisions existed names no revision number, so
    its revision is the latest one holding its specification.
    """

    if lineage.kind is not RevisionKind.WORKFLOW:
        return None

    state = production_states.get(lineage.id)

    if state is None:
        return None

    records = workflows.lineage(lineage.id)

    if state.specification_revision is not None:
        return next(
            (
                record.revision_digest
                for record in records
                if record.number == state.specification_revision
            ),
            None,
        )

    promoted = content_digest(state.specification)

    for record in reversed(records):
        revision = workflows.revision(lineage.id, record.number)

        if revision is not None and revision.content_digest == promoted:
            return record.revision_digest

    return None


def heads(
    request: HeadsRequest,
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
    production_states: WorkflowProductionStateRepository,
) -> HeadsResponse:
    """Return the head of each lineage asked about that is held, or of every one held."""

    asked = (
        tuple(dict.fromkeys(request.lineages))
        if request.lineages
        else tuple(held_lineages(workflows=workflows, tools=tools, benchmarks=benchmarks))
    )
    found: list[Head] = []

    for lineage in asked:
        chain = ancestry(
            lineage_records(lineage, workflows=workflows, tools=tools, benchmarks=benchmarks)
        )

        if not chain:
            continue

        found.append(
            Head(
                lineage=lineage,
                chain=tuple(record.revision_digest for record in chain),
                number=chain[-1].number,
                production_digest=production_digest(
                    lineage,
                    workflows=workflows,
                    production_states=production_states,
                ),
            )
        )

    return HeadsResponse(heads=tuple(found))


def portfolio_records(
    portfolio: ModelPortfolioRepository,
) -> PortfolioResponse:
    """Return the models a portfolio authorizes, with their declared data policies."""

    return PortfolioResponse(
        entries=tuple(
            PortfolioRecord(identifier=entry.identifier, data_policy=entry.data_policy)
            for entry in portfolio.entries()
        )
    )


def missing_credentials(
    request: CredentialsRequest,
    environ: Mapping[str, str],
    *,
    case_insensitive: bool = False,
) -> CredentialsResponse:
    """Return which names an environment does not set, in the order asked, each once.

    A grant ending in `*` is set when any variable it begins is set. An
    empty value counts as unset. On Windows, names match in any case, as
    a process tool's environment does (ADR 0099).
    """

    def is_set(name: str) -> bool:
        return any(
            value and grant_matches(name, variable, case_insensitive=case_insensitive)
            for variable, value in environ.items()
        )

    return CredentialsResponse(
        missing=tuple(name for name in dict.fromkeys(request.names) if not is_set(name))
    )


__all__ = [
    "heads",
    "held_lineages",
    "missing_credentials",
    "portfolio_records",
    "production_digest",
]
