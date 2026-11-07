"""The bytes of the content a prompt shows, as a provider sends them (ADR 0115).

A prompt names its content by handle. The engine checks that the run
received each piece, reads its bytes from the content store, and gives them
to the provider for the length of one completion; a provider reads them here
by digest, and never reaches the content store itself.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType

from azathoth.inputs import ContentRef
from azathoth.providers.exceptions import PromptContentError

_GIVEN_CONTENT: ContextVar[Mapping[str, bytes]] = ContextVar(
    "azathoth_prompt_content",
    default=MappingProxyType({}),
)


@contextmanager
def giving_prompt_content(
    contents: Mapping[str, bytes],
) -> Iterator[Mapping[str, bytes]]:
    """Give a provider the bytes of a prompt's content, by digest, inside the block.

    What was given before is restored afterwards.
    """

    given = MappingProxyType(dict(contents))
    token = _GIVEN_CONTENT.set(given)

    try:
        yield given
    finally:
        _GIVEN_CONTENT.reset(token)


def prompt_content_bytes(
    content: ContentRef,
    *,
    model: str,
) -> bytes:
    """Return the bytes of one piece of content a prompt shows, as given to its provider.

    Raises:
        PromptContentError: The bytes were not given.
    """

    given = _GIVEN_CONTENT.get().get(content.digest)

    if given is None:
        raise PromptContentError(
            f"Model {model} was not given the bytes of content {content.digest}."
        )

    return given


__all__ = [
    "giving_prompt_content",
    "prompt_content_bytes",
]
