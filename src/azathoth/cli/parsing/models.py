"""Model command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction

from azathoth.sensitivity import PolicyAnswer

MODEL_COMMAND = "model"

MODEL_ACTION_ATTRIBUTE = "model_action"

MODEL_AUTHORIZE_ACTION = "authorize"
MODEL_DEAUTHORIZE_ACTION = "deauthorize"
MODEL_LIST_ACTION = "list"
MODEL_POLICY_ACTION = "policy"
MODEL_PORTFOLIO_ACTION = "portfolio"
MODEL_SHOW_ACTION = "show"
MODEL_USAGE_ACTION = "usage"

MODEL_FORCE_ATTRIBUTE = "model_force"
MODEL_IDENTIFIER_ATTRIBUTE = "model_identifier"
MODEL_RETAINS_DATA_ATTRIBUTE = "model_retains_data"
MODEL_TRAINS_ON_DATA_ATTRIBUTE = "model_trains_on_data"

_ANSWERS = tuple(answer.value for answer in PolicyAnswer)


def _add_data_policy_arguments(
    parser: ArgumentParser,
) -> None:
    """Add the options that declare what a model's provider does with data (ADR 0123)."""

    retention = parser.add_mutually_exclusive_group()

    retention.add_argument(
        "--no-retention",
        dest=MODEL_RETAINS_DATA_ATTRIBUTE,
        action="store_const",
        const=PolicyAnswer.NO.value,
        help="Declare that the model's provider retains no data it is sent.",
    )

    retention.add_argument(
        "--retains-data",
        dest=MODEL_RETAINS_DATA_ATTRIBUTE,
        choices=_ANSWERS,
        help="Declare whether the model's provider retains data it is sent.",
    )

    training = parser.add_mutually_exclusive_group()

    training.add_argument(
        "--no-training",
        dest=MODEL_TRAINS_ON_DATA_ATTRIBUTE,
        action="store_const",
        const=PolicyAnswer.NO.value,
        help="Declare that the model's provider trains on no data it is sent.",
    )

    training.add_argument(
        "--trains-on-data",
        dest=MODEL_TRAINS_ON_DATA_ATTRIBUTE,
        choices=_ANSWERS,
        help="Declare whether the model's provider trains on data it is sent.",
    )


def add_model_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add model commands to the Azathoth parser."""

    model_parser = commands.add_parser(
        MODEL_COMMAND,
        help="Inspect and operate provider models.",
    )

    model_actions = model_parser.add_subparsers(
        dest=MODEL_ACTION_ATTRIBUTE,
    )

    model_authorize_parser = model_actions.add_parser(
        MODEL_AUTHORIZE_ACTION,
        help="Authorize one currently available provider model.",
    )

    model_authorize_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to authorize.",
    )

    _add_data_policy_arguments(model_authorize_parser)

    model_policy_parser = model_actions.add_parser(
        MODEL_POLICY_ACTION,
        help=(
            "Show, or declare, what an authorized model's provider does with data. Restricted "
            "input reaches only a model declared to neither retain nor train on data."
        ),
    )

    model_policy_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified identifier of an authorized model.",
    )

    _add_data_policy_arguments(model_policy_parser)

    model_deauthorize_parser = model_actions.add_parser(
        MODEL_DEAUTHORIZE_ACTION,
        help="Remove one model from organizational authorization.",
    )

    model_deauthorize_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to deauthorize.",
    )

    model_deauthorize_parser.add_argument(
        "--force",
        dest=MODEL_FORCE_ATTRIBUTE,
        action="store_true",
        help="Deauthorize even when active production depends on the model.",
    )

    model_actions.add_parser(
        MODEL_LIST_ACTION,
        help="List currently available provider models.",
    )

    model_actions.add_parser(
        MODEL_PORTFOLIO_ACTION,
        help="List models authorized for organizational selection.",
    )

    model_show_parser = model_actions.add_parser(
        MODEL_SHOW_ACTION,
        help="Show one currently available provider model.",
    )

    model_show_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to inspect.",
    )

    model_usage_parser = model_actions.add_parser(
        MODEL_USAGE_ACTION,
        help="Show where one model is configured, in production, and executed.",
    )

    model_usage_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to trace.",
    )
