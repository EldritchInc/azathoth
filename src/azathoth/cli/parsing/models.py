"""Model command-line parser construction."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction

MODEL_COMMAND = "model"

MODEL_ACTION_ATTRIBUTE = "model_action"

MODEL_AUTHORIZE_ACTION = "authorize"
MODEL_DEAUTHORIZE_ACTION = "deauthorize"
MODEL_LIST_ACTION = "list"
MODEL_PORTFOLIO_ACTION = "portfolio"
MODEL_SHOW_ACTION = "show"

MODEL_IDENTIFIER_ATTRIBUTE = "model_identifier"


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

    model_deauthorize_parser = model_actions.add_parser(
        MODEL_DEAUTHORIZE_ACTION,
        help="Remove one model from organizational authorization.",
    )

    model_deauthorize_parser.add_argument(
        MODEL_IDENTIFIER_ATTRIBUTE,
        metavar="MODEL_IDENTIFIER",
        help="Provider-qualified model identifier to deauthorize.",
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
