"""Model command dispatch for the Azathoth CLI."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast

from azathoth.cli.parsing import (
    MODEL_ACTION_ATTRIBUTE,
    MODEL_AUTHORIZE_ACTION,
    MODEL_DEAUTHORIZE_ACTION,
    MODEL_IDENTIFIER_ATTRIBUTE,
    MODEL_LIST_ACTION,
    MODEL_PORTFOLIO_ACTION,
    MODEL_SHOW_ACTION,
)

ModelIdentifierHandler = Callable[[str], int]
ModelListHandler = Callable[[], int]


def dispatch_model_command(
    arguments: Namespace,
    *,
    authorize_model: ModelIdentifierHandler,
    deauthorize_model: ModelIdentifierHandler,
    list_models: ModelListHandler,
    list_portfolio_models: ModelListHandler,
    show_model: ModelIdentifierHandler,
) -> int | None:
    """Dispatch one parsed model command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            MODEL_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == MODEL_AUTHORIZE_ACTION:
        model_identifier = cast(
            str,
            getattr(
                arguments,
                MODEL_IDENTIFIER_ATTRIBUTE,
            ),
        )

        return authorize_model(model_identifier)

    if action == MODEL_DEAUTHORIZE_ACTION:
        model_identifier = cast(
            str,
            getattr(
                arguments,
                MODEL_IDENTIFIER_ATTRIBUTE,
            ),
        )

        return deauthorize_model(model_identifier)

    if action == MODEL_LIST_ACTION:
        return list_models()

    if action == MODEL_PORTFOLIO_ACTION:
        return list_portfolio_models()

    if action == MODEL_SHOW_ACTION:
        model_identifier = cast(
            str,
            getattr(
                arguments,
                MODEL_IDENTIFIER_ATTRIBUTE,
            ),
        )

        return show_model(model_identifier)

    return None
