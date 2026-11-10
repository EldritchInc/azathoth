"""Tests for model data policies and which labels a model may receive (ADR 0123)."""

import pytest
from pydantic import ValidationError

from azathoth.sensitivity import (
    PRIVATE_DATA_POLICY,
    RESTRICTED_REFUSAL_HINT,
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    PolicyAnswer,
    Sensitivity,
    may_receive,
    restricted_refusal,
)

MODEL = "openrouter/example/frontier"


def test_policy_answers_are_yes_no_and_unknown() -> None:
    assert [answer.value for answer in PolicyAnswer] == ["yes", "no", "unknown"]


def test_a_policy_is_unknown_until_declared() -> None:
    assert DataPolicy() == UNKNOWN_DATA_POLICY
    assert UNKNOWN_DATA_POLICY.retains_data is PolicyAnswer.UNKNOWN
    assert UNKNOWN_DATA_POLICY.trains_on_data is PolicyAnswer.UNKNOWN
    assert UNKNOWN_DATA_POLICY.unknown


def test_a_private_policy_neither_retains_nor_trains() -> None:
    assert (
        DataPolicy(
            retains_data=PolicyAnswer.NO,
            trains_on_data=PolicyAnswer.NO,
        )
        == PRIVATE_DATA_POLICY
    )
    assert PRIVATE_DATA_POLICY.private
    assert not PRIVATE_DATA_POLICY.unknown


@pytest.mark.parametrize(
    ("retains", "trains"),
    [
        (PolicyAnswer.YES, PolicyAnswer.NO),
        (PolicyAnswer.NO, PolicyAnswer.YES),
        (PolicyAnswer.UNKNOWN, PolicyAnswer.NO),
        (PolicyAnswer.NO, PolicyAnswer.UNKNOWN),
        (PolicyAnswer.YES, PolicyAnswer.YES),
    ],
)
def test_only_no_and_no_is_private(
    retains: PolicyAnswer,
    trains: PolicyAnswer,
) -> None:
    policy = DataPolicy(retains_data=retains, trains_on_data=trains)

    assert not policy.private
    assert not policy.unknown


def test_a_policy_is_frozen_and_closed() -> None:
    field = "retains_data"

    with pytest.raises(ValidationError):
        setattr(PRIVATE_DATA_POLICY, field, PolicyAnswer.YES)

    with pytest.raises(ValidationError):
        DataPolicy.model_validate({"retains_data": "no", "shares_data": "no"})


def test_a_policy_reads_its_answers_from_json() -> None:
    assert DataPolicy.model_validate_json('{"retains_data":"no","trains_on_data":"no"}') == (
        PRIVATE_DATA_POLICY
    )


@pytest.mark.parametrize("label", [Sensitivity.PUBLIC, Sensitivity.INTERNAL, None])
@pytest.mark.parametrize(
    "policy",
    [None, UNKNOWN_DATA_POLICY, DataPolicy(retains_data=PolicyAnswer.YES)],
)
def test_any_model_may_receive_public_and_internal_data(
    label: Sensitivity | None,
    policy: DataPolicy | None,
) -> None:
    assert may_receive(policy, label)


def test_only_a_private_model_may_receive_restricted_data() -> None:
    assert may_receive(PRIVATE_DATA_POLICY, Sensitivity.RESTRICTED)
    assert not may_receive(UNKNOWN_DATA_POLICY, Sensitivity.RESTRICTED)
    assert not may_receive(None, Sensitivity.RESTRICTED)
    assert not may_receive(
        DataPolicy(retains_data=PolicyAnswer.NO, trains_on_data=PolicyAnswer.YES),
        Sensitivity.RESTRICTED,
    )


@pytest.mark.parametrize(
    ("policy", "reasons"),
    [
        (None, "it is not in the portfolio"),
        (
            UNKNOWN_DATA_POLICY,
            "its portfolio entry does not say whether its provider retains data, "
            "and does not say whether it trains on data",
        ),
        (
            DataPolicy(retains_data=PolicyAnswer.YES, trains_on_data=PolicyAnswer.NO),
            "its portfolio entry says its provider retains data",
        ),
        (
            DataPolicy(retains_data=PolicyAnswer.NO, trains_on_data=PolicyAnswer.YES),
            "its portfolio entry says its provider trains on data",
        ),
        (
            DataPolicy(retains_data=PolicyAnswer.NO, trains_on_data=PolicyAnswer.UNKNOWN),
            "its portfolio entry does not say whether its provider trains on data",
        ),
        (
            DataPolicy(retains_data=PolicyAnswer.YES, trains_on_data=PolicyAnswer.YES),
            "its portfolio entry says its provider retains data, and says it trains on data",
        ),
        (
            DataPolicy(retains_data=PolicyAnswer.UNKNOWN, trains_on_data=PolicyAnswer.YES),
            "its portfolio entry does not say whether its provider retains data, "
            "and says it trains on data",
        ),
    ],
)
def test_a_refusal_says_why_the_model_may_not_receive_restricted_data(
    policy: DataPolicy | None,
    reasons: str,
) -> None:
    assert (
        restricted_refusal(MODEL, policy) == f"{MODEL} cannot receive restricted input: {reasons}."
    )


def test_a_private_model_has_no_refusal() -> None:
    with pytest.raises(ValueError) as caught:
        restricted_refusal(MODEL, PRIVATE_DATA_POLICY)

    assert str(caught.value) == f"{MODEL} may receive restricted input."


def test_the_refusal_hint_names_how_to_declare_a_policy_or_choose_another_model() -> None:
    assert RESTRICTED_REFUSAL_HINT.format(model=MODEL) == (
        f"If its provider neither retains nor trains on data, declare that with "
        f"`azathoth model policy {MODEL} --no-retention --no-training`; "
        "otherwise choose a model that may receive restricted input."
    )
