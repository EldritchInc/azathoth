"""Installing the standard tool library that ships with Azathoth (ADR 0095).

`azathoth init`, `azathoth tool install-standard`, `api.initialize` and the
service API's `tools.install_standard` all install it here, the same way.
"""

from collections.abc import Callable

from azathoth.api.errors import ConflictError
from azathoth.api.models import StandardTool
from azathoth.revisions import content_digest
from azathoth.standard import STANDARD_TOOL_AUTHOR, standard_tool_documents
from azathoth.tools import ToolRepository
from azathoth.tools.revision import earliest_identical_tool_revision


def install_standard_tools(
    repository: ToolRepository,
    *,
    each: Callable[[StandardTool], object] | None = None,
) -> tuple[StandardTool, ...]:
    """Install each standard tool whose current revision is not the standard document.

    Each standard document is compared with the latest revision of its exact
    tool version. A version that is not there is imported as its first
    revision. A version whose latest revision has the same content digest is
    left alone, and nothing is written. A version whose latest revision
    differs, such as an operator's modified copy, gets the standard document
    as its next revision, which becomes current. Installing again is always
    safe.

    The documents are installed in their fixed order, and the first that
    cannot be saved stops the installation. `each` is told of each tool as
    it is installed or found, so what was done before a failure is known.

    Raises:
        ConflictError: An artifact ID of a standard document belongs to
            another tool or version here.
    """

    tools: list[StandardTool] = []

    for document in standard_tool_documents():
        definition = document.definition
        latest = repository.latest_document_revision(definition.id, definition.version)

        if latest is not None and latest.content_digest == content_digest(document):
            tools.append(
                StandardTool(
                    name=definition.name,
                    version=definition.version,
                    revision=latest.number,
                    installed=False,
                )
            )

            if each is not None:
                each(tools[-1])

            continue

        try:
            revision = repository.save_document(document, author=STANDARD_TOOL_AUTHOR)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

        identical = earliest_identical_tool_revision(
            repository.document_revisions(revision.tool_id),
            revision,
        )

        tools.append(
            StandardTool(
                name=definition.name,
                version=definition.version,
                revision=revision.number,
                installed=True,
                identical_to=None if identical is None else identical.number,
            )
        )

        if each is not None:
            each(tools[-1])

    return tuple(tools)


__all__ = [
    "install_standard_tools",
]
