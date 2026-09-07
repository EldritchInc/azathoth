"""Tool command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from azathoth.cli.parsing import (
    TOOL_ACTION_ATTRIBUTE,
    TOOL_DOCUMENT_ATTRIBUTE,
    TOOL_ID_ATTRIBUTE,
    TOOL_IMPLEMENTATION_ID_ATTRIBUTE,
    TOOL_IMPLEMENTATION_SHOW_ACTION,
    TOOL_IMPLEMENTATIONS_ACTION,
    TOOL_IMPORT_ACTION,
    TOOL_LIST_ACTION,
    TOOL_SHOW_ACTION,
    TOOL_TEST_CASE_ID_ATTRIBUTE,
    TOOL_TEST_CASE_SHOW_ACTION,
    TOOL_TEST_CASES_ACTION,
    TOOL_VERIFY_ACTION,
    TOOL_VERSION_ATTRIBUTE,
    TOOL_VERSIONS_ACTION,
)

ToolIdentifierHandler = Callable[[UUID], int]
ToolImportHandler = Callable[[Path], int]
ToolListHandler = Callable[[], int]
ToolVersionHandler = Callable[..., int]


def dispatch_tool_command(
    arguments: Namespace,
    *,
    import_tool: ToolImportHandler,
    list_tool_implementations: ToolVersionHandler,
    list_tool_test_cases: ToolIdentifierHandler,
    list_tool_versions: ToolIdentifierHandler,
    list_tools: ToolListHandler,
    show_tool: ToolVersionHandler,
    show_tool_implementation: ToolIdentifierHandler,
    show_tool_test_case: ToolIdentifierHandler,
    verify_tool: ToolVersionHandler,
) -> int | None:
    """Dispatch one parsed tool command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            TOOL_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == TOOL_LIST_ACTION:
        return list_tools()

    if action == TOOL_IMPORT_ACTION:
        return import_tool(
            cast(
                Path,
                getattr(
                    arguments,
                    TOOL_DOCUMENT_ATTRIBUTE,
                ),
            )
        )

    if action == TOOL_SHOW_ACTION:
        return show_tool(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_ID_ATTRIBUTE,
                ),
            ),
            version=cast(
                str,
                getattr(
                    arguments,
                    TOOL_VERSION_ATTRIBUTE,
                ),
            ),
        )

    if action == TOOL_VERSIONS_ACTION:
        return list_tool_versions(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_ID_ATTRIBUTE,
                ),
            )
        )

    if action == TOOL_IMPLEMENTATIONS_ACTION:
        return list_tool_implementations(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_ID_ATTRIBUTE,
                ),
            ),
            version=cast(
                str,
                getattr(
                    arguments,
                    TOOL_VERSION_ATTRIBUTE,
                ),
            ),
        )

    if action == TOOL_IMPLEMENTATION_SHOW_ACTION:
        return show_tool_implementation(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_IMPLEMENTATION_ID_ATTRIBUTE,
                ),
            )
        )

    if action == TOOL_TEST_CASES_ACTION:
        return list_tool_test_cases(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_ID_ATTRIBUTE,
                ),
            )
        )

    if action == TOOL_TEST_CASE_SHOW_ACTION:
        return show_tool_test_case(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_TEST_CASE_ID_ATTRIBUTE,
                ),
            )
        )

    if action == TOOL_VERIFY_ACTION:
        return verify_tool(
            cast(
                UUID,
                getattr(
                    arguments,
                    TOOL_ID_ATTRIBUTE,
                ),
            ),
            version=cast(
                str,
                getattr(
                    arguments,
                    TOOL_VERSION_ATTRIBUTE,
                ),
            ),
        )

    return None
