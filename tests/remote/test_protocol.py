"""Tests for what a remote and its client agree on before anything travels (ADR 0124)."""

import pytest
from pydantic import ValidationError

from azathoth.remote import (
    DEFAULT_EDITION,
    MAX_CONTENT_BYTES,
    MAX_PUSH_BYTES,
    PROTOCOL_VERSION,
    Capabilities,
    ProtocolMismatchError,
    require_protocol,
)


def capabilities(
    protocol: int = PROTOCOL_VERSION,
) -> Capabilities:
    return Capabilities(protocol=protocol, azathoth_version="1.4.0a5", schema_version=5)


def test_the_protocol_and_limits_are_pinned() -> None:
    assert PROTOCOL_VERSION == 1
    assert DEFAULT_EDITION == "community"
    assert MAX_PUSH_BYTES == 64 * 1024 * 1024
    assert MAX_CONTENT_BYTES == 10 * 1024 * 1024


def test_capabilities_default_to_a_community_remote_that_refuses_restricted_data() -> None:
    shown = capabilities()

    assert (shown.edition, shown.plugins, shown.accepts_restricted) == ("community", {}, False)
    assert shown.model_dump(mode="json") == {
        "protocol": 1,
        "azathoth_version": "1.4.0a5",
        "schema_version": 5,
        "edition": "community",
        "plugins": {},
        "accepts_restricted": False,
    }


def test_capabilities_are_closed() -> None:
    with pytest.raises(ValidationError):
        Capabilities.model_validate(
            {**capabilities().model_dump(mode="json"), "streams": True},
        )


def test_the_same_protocol_is_accepted() -> None:
    shown = capabilities()

    assert shown.require_protocol() is shown
    require_protocol(PROTOCOL_VERSION)


def test_another_protocol_is_refused_naming_both() -> None:
    with pytest.raises(ProtocolMismatchError) as caught:
        capabilities(2).require_protocol()

    assert str(caught.value) == (
        "The remote speaks remote protocol 2, and this Azathoth speaks remote protocol 1; run "
        "versions of Azathoth that speak the same protocol on both."
    )


def test_a_remote_names_its_client_as_the_peer() -> None:
    with pytest.raises(ProtocolMismatchError, match=r"^The client speaks remote protocol 0,"):
        require_protocol(0, peer="The client")
