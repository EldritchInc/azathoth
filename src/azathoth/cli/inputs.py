"""Workflow inputs given to the CLI as files (ADR 0096)."""

from dataclasses import dataclass
from pathlib import Path

from azathoth.inputs import (
    FILE_SCHEME,
    FileInputResolver,
    InputPolicy,
    InputSourceError,
    ReferenceInput,
    ResolvedInput,
    SQLiteContentStore,
    file_uri,
    infer_media_type,
    resolve_input,
)

CLI_INPUT_POLICY = InputPolicy(
    resolvers={FILE_SCHEME: FileInputResolver()},
)
"""The CLI accepts local files, within the default size cap."""


@dataclass(frozen=True)
class WorkflowInputFile:
    """A file an operator gave as a workflow's input.

    Without a media type, the file's extension decides it.
    """

    path: Path
    media_type: str | None = None


def input_file_source(
    input_file: WorkflowInputFile,
) -> ReferenceInput:
    """Return the reference one input file stands for.

    Raises:
        InputSourceError: No media type was given and the file's extension
            implies none.
    """

    media_type = input_file.media_type or infer_media_type(input_file.path.name)

    if media_type is None:
        raise InputSourceError(
            f"Cannot tell the media type of {input_file.path} from its extension; "
            "give it with --media-type."
        )

    return ReferenceInput(
        uri=file_uri(input_file.path),
        media_type=media_type,
    )


def resolve_input_file(
    input_file: WorkflowInputFile,
    *,
    database: Path,
) -> ResolvedInput:
    """Resolve one input file under the CLI's policy, storing its content.

    Raises:
        InputSourceError: The file's media type cannot be told.
        InputResolutionError: The file cannot be read, is too large, or does
            not decode as its media type.
    """

    return resolve_input(
        input_file_source(input_file),
        policy=CLI_INPUT_POLICY,
        store=SQLiteContentStore(database),
    )


__all__ = [
    "CLI_INPUT_POLICY",
    "WorkflowInputFile",
    "input_file_source",
    "resolve_input_file",
]
