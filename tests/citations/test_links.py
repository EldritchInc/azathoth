"""Tests that an anchor's origin becomes a link to its place (ADR 0117)."""

import importlib
from typing import Any

import pytest

from azathoth.citations import (
    DEFAULT_LINK_EXPIRY_SECONDS,
    LINK_EXPIRY_VARIABLE,
    MAX_LINK_EXPIRY_SECONDS,
    MISSING_LINK_EXTRA_MESSAGE,
    FragmentSelector,
    LinkResolutionError,
    OriginLinkResolver,
    S3LinkResolver,
    SourceAnchor,
    TextQuoteSelector,
    default_link_resolvers,
    link_expiry_seconds,
    page_fragment,
    resolve_link,
)
from azathoth.citations.selectors import MEDIA_FRAGMENT_SPECIFICATION, PDF_FRAGMENT_SPECIFICATION
from azathoth.inputs import InputOrigin, InputUnavailableError, content_bytes_digest

DIGEST = content_bytes_digest(b"%PDF-1.7")


def anchor(
    origin: InputOrigin | None,
    *fragments: FragmentSelector,
    media_type: str = "application/pdf",
) -> SourceAnchor:
    """Return an anchor of a PDF, from some origin, at some fragments."""

    return SourceAnchor(
        digest=DIGEST,
        media_type=media_type,
        origin=origin,
        selectors=fragments
        or (FragmentSelector(value="page=3", conformsTo=PDF_FRAGMENT_SPECIFICATION),),
    )


def pdf(
    value: str,
) -> FragmentSelector:
    """Return a PDF fragment selector."""

    return FragmentSelector(value=value, conformsTo=PDF_FRAGMENT_SPECIFICATION)


S3 = InputOrigin(uri="s3://claims-intake/2026/11/claim%200412.pdf", version_id="3HL4.kq")


@pytest.mark.parametrize(
    ("fragments", "expected"),
    [
        pytest.param((pdf("page=3"),), "#page=3", id="a-page"),
        pytest.param((pdf("page=12&viewrect=72,90,450,14"),), "#page=12", id="a-box"),
        pytest.param((pdf("viewrect=72,90,450,14&page=4"),), "#page=4", id="page-last"),
        pytest.param((pdf("viewrect=72,90,450,14"),), "", id="no-page"),
        pytest.param((pdf("page=0"),), "", id="page-zero"),
        pytest.param((pdf("pages=3"),), "", id="not-the-page-parameter"),
        pytest.param((pdf("zoom=2&xpage=3"),), "", id="a-parameter-ending-in-page"),
    ],
)
def test_a_pdf_fragment_links_to_its_page(
    fragments: tuple[FragmentSelector, ...],
    expected: str,
) -> None:
    assert page_fragment(anchor(None, *fragments)) == expected


def test_an_anchor_without_a_pdf_fragment_links_to_no_page() -> None:
    image = anchor(
        None,
        FragmentSelector(value="xywh=1,2,3,4", conformsTo=MEDIA_FRAGMENT_SPECIFICATION),
        media_type="image/png",
    )

    assert page_fragment(image) == ""


def test_a_media_fragment_naming_a_page_names_no_page_of_a_pdf() -> None:
    assert (
        page_fragment(
            anchor(
                None,
                FragmentSelector(value="page=2", conformsTo=MEDIA_FRAGMENT_SPECIFICATION),
                media_type="image/png",
            )
        )
        == ""
    )


def test_a_text_selector_names_no_page() -> None:
    texted = SourceAnchor.model_validate(
        {
            "digest": DIGEST,
            "media_type": "application/pdf",
            "selectors": [
                TextQuoteSelector(exact="x").model_dump(mode="json", by_alias=True),
                pdf("page=2").model_dump(mode="json", by_alias=True),
            ],
            "extraction": {"tool": "segment_pdf", "version": "1.0.0", "digest": DIGEST},
        }
    )

    assert page_fragment(texted) == "#page=2"


def test_an_origin_that_is_a_url_links_to_its_page() -> None:
    resolver = OriginLinkResolver()

    assert resolver.link(anchor(InputOrigin(uri="https://claims.test/0412.pdf"))) == (
        "https://claims.test/0412.pdf#page=3"
    )
    assert resolver.link(anchor(None)) is None


class RecordingClient:
    """An S3 client that signs links by naming what it was asked to sign."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], int]] = []

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict[str, Any],
        ExpiresIn: int,
    ) -> str:
        """Record the request and return a stand-in link."""

        self.calls.append((operation, Params, ExpiresIn))

        return "https://signed.test/claim"


def test_an_s3_origin_links_by_a_presigned_get_of_its_version() -> None:
    client = RecordingClient()
    resolver = S3LinkResolver(expires_in=600, client=client)

    assert resolver.link(anchor(S3)) == "https://signed.test/claim#page=3"
    assert client.calls == [
        (
            "get_object",
            {"Bucket": "claims-intake", "Key": "2026/11/claim 0412.pdf", "VersionId": "3HL4.kq"},
            600,
        )
    ]


def test_an_s3_origin_with_no_version_links_to_the_object() -> None:
    client = RecordingClient()

    S3LinkResolver(client=client).link(anchor(InputOrigin(uri="s3://claims-intake/a.pdf")))

    assert client.calls == [
        ("get_object", {"Bucket": "claims-intake", "Key": "a.pdf"}, DEFAULT_LINK_EXPIRY_SECONDS)
    ]


def test_an_s3_resolver_makes_its_client_once_and_only_when_asked() -> None:
    made: list[RecordingClient] = []

    def factory() -> RecordingClient:
        made.append(RecordingClient())

        return made[-1]

    resolver = S3LinkResolver(client_factory=factory)

    assert made == []
    assert resolver.link(anchor(None)) is None
    assert made == []

    resolver.link(anchor(S3))
    resolver.link(anchor(S3))

    assert len(made) == 1
    assert len(made[0].calls) == 2


def test_an_s3_link_without_boto3_says_which_extra_to_install() -> None:
    def missing() -> Any:
        raise InputUnavailableError("no boto3")

    with pytest.raises(LinkResolutionError) as raised:
        S3LinkResolver(client_factory=missing).link(anchor(S3))

    assert (
        str(raised.value)
        == MISSING_LINK_EXTRA_MESSAGE
        == (
            "Links to s3:// documents need boto3, which is not installed; install "
            "azathoth-ai[worker]."
        )
    )


def test_an_s3_link_s3_will_not_sign_says_why() -> None:
    class Refusing:
        def generate_presigned_url(self, *_: Any, **__: Any) -> str:
            raise RuntimeError("Unable to locate credentials")

    with pytest.raises(LinkResolutionError) as raised:
        S3LinkResolver(client=Refusing()).link(anchor(S3))

    assert str(raised.value) == (
        f"A link to {S3.uri} could not be signed: Unable to locate credentials"
    )


def test_a_real_presigned_link_names_its_version_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("boto3")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    client = importlib.import_module("boto3").session.Session().client("s3")
    link = S3LinkResolver(expires_in=900, client=client).link(anchor(S3))

    assert link is not None
    assert link.startswith("https://claims-intake.s3.amazonaws.com/2026/11/claim%200412.pdf?")
    assert "versionId=3HL4.kq" in link
    assert "Signature=" in link
    assert link.endswith("#page=3")


@pytest.mark.parametrize(
    ("environment", "seconds"),
    [
        pytest.param({}, DEFAULT_LINK_EXPIRY_SECONDS, id="unset"),
        pytest.param({LINK_EXPIRY_VARIABLE: "  "}, DEFAULT_LINK_EXPIRY_SECONDS, id="blank"),
        pytest.param({LINK_EXPIRY_VARIABLE: "1"}, 1, id="shortest"),
        pytest.param({LINK_EXPIRY_VARIABLE: "604800"}, MAX_LINK_EXPIRY_SECONDS, id="longest"),
    ],
)
def test_a_links_expiry_is_an_hour_unless_the_environment_says(
    environment: dict[str, str],
    seconds: int,
) -> None:
    assert link_expiry_seconds(environment) == seconds


@pytest.mark.parametrize("value", ["0", "604801", "an hour", "1.5", "-3"])
def test_an_expiry_that_is_not_one_is_refused(
    value: str,
) -> None:
    with pytest.raises(LinkResolutionError) as raised:
        link_expiry_seconds({LINK_EXPIRY_VARIABLE: value})

    assert str(raised.value) == (
        "AZATHOTH_LINK_EXPIRY_SECONDS must be a whole number of seconds from 1 to 604800, "
        f"not {value!r}."
    )


def test_azathoth_links_to_web_file_and_s3_origins() -> None:
    resolvers = default_link_resolvers(expires_in=60)

    assert set(resolvers) == {"http", "https", "file", "s3"}
    assert isinstance(resolvers["s3"], S3LinkResolver)
    assert resolvers["s3"].expires_in == 60
    assert all(
        isinstance(resolvers[scheme], OriginLinkResolver) for scheme in ("http", "https", "file")
    )


def test_a_link_is_made_by_the_resolver_of_its_origins_scheme() -> None:
    resolvers = default_link_resolvers()

    assert resolve_link(anchor(InputOrigin(uri="file:///claims/0412.pdf")), resolvers) == (
        "file:///claims/0412.pdf#page=3"
    )
    assert resolve_link(anchor(InputOrigin(uri="gs://claims/0412.pdf")), resolvers) is None
    assert resolve_link(anchor(None), resolvers) is None
