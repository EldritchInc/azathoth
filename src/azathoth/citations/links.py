"""Links a person can open to the place an anchor names (ADR 0117).

An anchor names its document by digest, and by the origin its content came
from when one was recorded. A link resolver turns that origin into a URL
that opens the very document, at the page the anchor's PDF fragment names,
`#page=N`, which PDF viewers follow:

- `http`, `https` and `file` origins are links already, and gain the page;
- an `s3` origin becomes a presigned GET of the recorded object version,
  which expires, so it is made when it is asked for and never kept.

An anchor with no origin, or whose origin no resolver reads, has no link.
"""

import os
import re
from collections.abc import Callable, Mapping
from typing import Any, Final, Protocol
from urllib.parse import unquote, urlsplit

from azathoth.citations.anchors import SourceAnchor
from azathoth.citations.selectors import PDF_FRAGMENT_SPECIFICATION, FragmentSelector
from azathoth.inputs import InputUnavailableError, s3_client

LINK_EXPIRY_VARIABLE: Final = "AZATHOTH_LINK_EXPIRY_SECONDS"
"""The environment variable naming how long a presigned link stays valid, in seconds."""

DEFAULT_LINK_EXPIRY_SECONDS: Final = 3600
"""How long a presigned link stays valid when nothing says otherwise: one hour."""

MAX_LINK_EXPIRY_SECONDS: Final = 604800
"""The longest S3 lets a presigned link stay valid: seven days."""

MISSING_LINK_EXTRA_MESSAGE: Final = (
    "Links to s3:// documents need boto3, which is not installed; install azathoth-ai[worker]."
)
"""What resolving an `s3://` link without boto3 reports."""

_PAGE: Final = re.compile(r"(?:^|&)page=([1-9][0-9]*)(?:&|$)")


class LinkResolutionError(ValueError):
    """Raised when a link cannot be made, or its expiry is not valid."""


class LinkResolver(Protocol):
    """Turn an anchor whose origin has one scheme into a link, or into none."""

    def link(
        self,
        anchor: SourceAnchor,
    ) -> str | None:
        """Return a URL opening the anchor's document at its place, or None.

        Raises:
            LinkResolutionError: The link cannot be made.
        """
        ...


def page_fragment(
    anchor: SourceAnchor,
) -> str:
    """Return `#page=N` for the page an anchor's PDF fragment names, or nothing."""

    for selector in anchor.selectors:
        if (
            isinstance(selector, FragmentSelector)
            and selector.conformsTo == PDF_FRAGMENT_SPECIFICATION
            and (page := _PAGE.search(selector.value)) is not None
        ):
            return f"#page={page.group(1)}"

    return ""


class OriginLinkResolver:
    """Link to an origin that is a URL already, as `https` and `file` origins are."""

    def link(
        self,
        anchor: SourceAnchor,
    ) -> str | None:
        """Return the origin's URI at the anchor's page, or None without an origin."""

        if anchor.origin is None:
            return None

        return f"{anchor.origin.uri}{page_fragment(anchor)}"


class S3LinkResolver:
    """Link to an `s3://` origin by a presigned GET of its recorded object version."""

    def __init__(
        self,
        *,
        expires_in: int = DEFAULT_LINK_EXPIRY_SECONDS,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Sign links valid for `expires_in` seconds, with a client made when first needed."""

        self.expires_in = expires_in
        self._client: Any | None = client
        self._client_factory = client_factory if client_factory is not None else s3_client

    def link(
        self,
        anchor: SourceAnchor,
    ) -> str | None:
        """Return a presigned GET of the anchor's object, its version when recorded, at its page.

        Raises:
            LinkResolutionError: boto3 is not installed, or S3 would not sign
                the link.
        """

        if anchor.origin is None:
            return None

        parts = urlsplit(anchor.origin.uri)
        parameters: dict[str, str] = {
            "Bucket": parts.netloc,
            "Key": unquote(parts.path.removeprefix("/")),
        }

        if anchor.origin.version_id is not None:
            parameters["VersionId"] = anchor.origin.version_id

        try:
            signed = self._signing_client().generate_presigned_url(
                "get_object",
                Params=parameters,
                ExpiresIn=self.expires_in,
            )
        except InputUnavailableError as exc:
            raise LinkResolutionError(MISSING_LINK_EXTRA_MESSAGE) from exc
        except Exception as exc:
            raise LinkResolutionError(
                f"A link to {anchor.origin.uri} could not be signed: {exc}"
            ) from exc

        return f"{signed}{page_fragment(anchor)}"

    def _signing_client(
        self,
    ) -> Any:
        """Return the client links are signed with, making it on first use."""

        if self._client is None:
            self._client = self._client_factory()

        return self._client


def link_expiry_seconds(
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Return how long presigned links stay valid, as `AZATHOTH_LINK_EXPIRY_SECONDS` says.

    Raises:
        LinkResolutionError: The variable is not a whole number of seconds
            from 1 to seven days.
    """

    value = environment.get(LINK_EXPIRY_VARIABLE)

    if value is None or not value.strip():
        return DEFAULT_LINK_EXPIRY_SECONDS

    try:
        seconds = int(value)
    except ValueError:
        seconds = 0

    if not 1 <= seconds <= MAX_LINK_EXPIRY_SECONDS:
        raise LinkResolutionError(
            f"{LINK_EXPIRY_VARIABLE} must be a whole number of seconds from 1 to "
            f"{MAX_LINK_EXPIRY_SECONDS}, not {value!r}."
        )

    return seconds


def default_link_resolvers(
    *,
    expires_in: int = DEFAULT_LINK_EXPIRY_SECONDS,
) -> dict[str, LinkResolver]:
    """Return the resolvers of every scheme Azathoth links to, by scheme."""

    origin = OriginLinkResolver()

    return {
        "http": origin,
        "https": origin,
        "file": origin,
        "s3": S3LinkResolver(expires_in=expires_in),
    }


def resolve_link(
    anchor: SourceAnchor,
    resolvers: Mapping[str, LinkResolver],
) -> str | None:
    """Return a link to an anchor's place by the resolver of its origin's scheme, or None.

    Raises:
        LinkResolutionError: The resolver cannot make the link.
    """

    if anchor.origin is None:
        return None

    resolver = resolvers.get(urlsplit(anchor.origin.uri).scheme)

    return resolver.link(anchor) if resolver is not None else None


__all__ = [
    "DEFAULT_LINK_EXPIRY_SECONDS",
    "LINK_EXPIRY_VARIABLE",
    "MAX_LINK_EXPIRY_SECONDS",
    "MISSING_LINK_EXTRA_MESSAGE",
    "LinkResolutionError",
    "LinkResolver",
    "OriginLinkResolver",
    "S3LinkResolver",
    "default_link_resolvers",
    "link_expiry_seconds",
    "page_fragment",
    "resolve_link",
]
