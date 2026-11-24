"""The model commands on a remote, reported as they are on this machine (ADR 0140).

`model list`, `model show`, `model portfolio`, `model authorize`, `model
policy` and `model deauthorize` given `--remote` ask that remote's service
API, so the models are those the remote's providers serve and the
portfolio is the remote's, and print each line the command prints here.
What the remote records, an authorization or a declared policy, is
recorded as the caller its token names.
"""

import sys
from collections.abc import Sequence

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering.production_views import author_text
from azathoth.cli.service import service_instance
from azathoth.sensitivity import DataPolicy, PolicyAnswer


def _instance() -> api.Instance:
    """Return the instance connected to the remote `--remote` chose.

    Raises:
        ApiError: The remote cannot be found, or its token is not set.
    """

    return service_instance(CliRuntimeConfiguration.from_environment())


def _refused(
    exc: api.ApiError,
) -> int:
    """Print why the remote refused a call, and return the exit status that says so."""

    print(str(exc), file=sys.stderr)

    return 1


def list_models_on_remote() -> int:
    """List the models a remote's providers serve now, as `model list` lists them here."""

    try:
        models = _instance().models.list()
    except api.ApiError as exc:
        return _refused(exc)

    for model in models:
        print(f"{model.identifier}  {model.display_name}")

    return 0


def _values(
    values: Sequence[str],
) -> str:
    """Render a model's modalities or capabilities, or `none`."""

    return ", ".join(values) if values else "none"


def _integer(
    value: int | None,
) -> str:
    """Render a model's limit, or that it is unknown."""

    return "unknown" if value is None else str(value)


def show_model_on_remote(
    identifier: str,
) -> int:
    """Show one model a remote's providers serve now, as `model show` shows it here."""

    try:
        model = _instance().models.get(identifier)
    except api.ApiError as exc:
        return _refused(exc)

    print(f"ID: {model.identifier}")
    print(f"Provider: {model.provider}")
    print(f"Model: {model.model}")
    print(f"Name: {model.display_name}")
    print(f"Input Modalities: {_values(model.input_modalities)}")
    print(f"Output Modalities: {_values(model.output_modalities)}")
    print(f"Capabilities: {_values(model.capabilities)}")
    print(f"Context Window: {_integer(model.context_window_tokens)}")
    print(f"Maximum Output Tokens: {_integer(model.maximum_output_tokens)}")

    if model.input_usd_per_million_tokens is None or model.output_usd_per_million_tokens is None:
        print("Input Price: unknown")
        print("Output Price: unknown")

        return 0

    print(f"Input Price: ${model.input_usd_per_million_tokens:.6f} per million tokens")
    print(f"Output Price: ${model.output_usd_per_million_tokens:.6f} per million tokens")

    return 0


def list_portfolio_on_remote() -> int:
    """List the models a remote authorizes, as `model portfolio` lists them here."""

    try:
        entries = _instance().portfolio.list()
    except api.ApiError as exc:
        return _refused(exc)

    for entry in entries:
        print(entry.identifier)

    return 0


def authorize_model_on_remote(
    identifier: str,
    *,
    data_policy: DataPolicy,
) -> int:
    """Authorize one model a remote's providers serve, as `model authorize` does here."""

    try:
        _instance().portfolio.add(identifier, data_policy=data_policy)
    except api.ApiError as exc:
        return _refused(exc)

    print(f"Authorized model {identifier}.")

    return 0


def _print_data_policy(
    entry: api.PortfolioEntry,
) -> None:
    """Render what a remote's entry declares its provider does with data, and who declared it."""

    policy = entry.data_policy

    print(f"Retains Data: {policy.retains_data.value}")
    print(f"Trains On Data: {policy.trains_on_data.value}")
    print(f"Restricted Input: {'allowed' if entry.receives_restricted else 'refused'}")

    if entry.policy_declared_at is not None:
        declared_by = entry.policy_declared_by

        print(f"Declared By: {'unknown' if declared_by is None else author_text(declared_by)}")
        print(f"Declared At: {entry.policy_declared_at.isoformat()}")


def model_policy_on_remote(
    identifier: str,
    *,
    retains_data: PolicyAnswer | None,
    trains_on_data: PolicyAnswer | None,
) -> int:
    """Show, or declare, one authorized model's data policy on a remote, as `model policy` does.

    An answer not given keeps the one the remote declares.
    """

    try:
        instance = _instance()
        entry = next(
            (entry for entry in instance.portfolio.list() if entry.identifier == identifier),
            None,
        )

        if entry is None:
            print(f"Model {identifier!r} is not authorized.", file=sys.stderr)

            return 1

        if retains_data is None and trains_on_data is None:
            _print_data_policy(entry)

            return 0

        declared = instance.portfolio.set_data_policy(
            identifier,
            DataPolicy(
                retains_data=entry.data_policy.retains_data
                if retains_data is None
                else retains_data,
                trains_on_data=entry.data_policy.trains_on_data
                if trains_on_data is None
                else trains_on_data,
            ),
        )
    except api.ApiError as exc:
        return _refused(exc)

    print(f"Declared the data policy of model {identifier}.")

    _print_data_policy(declared)

    return 0


def _print_dependents(
    dependents: Sequence[api.ProductionDependent],
) -> None:
    """Report the production workflows a model is used by, as `model deauthorize` does here."""

    for dependent in dependents:
        roles = ", ".join(f"{usage.role} step {usage.step_id}" for usage in dependent.steps)

        print(
            f"  {dependent.workflow_name} ({dependent.workflow_id}): {roles}",
            file=sys.stderr,
        )


def deauthorize_model_on_remote(
    identifier: str,
    *,
    force: bool,
) -> int:
    """Remove one model from a remote's portfolio, as `model deauthorize` does here."""

    try:
        removal = _instance().portfolio.remove(identifier, force=force)
    except api.ModelInUseError as exc:
        print(
            f"Model {identifier!r} is used by active production and was not deauthorized.",
            file=sys.stderr,
        )
        _print_dependents(exc.dependents)
        print("Use --force to deauthorize anyway.", file=sys.stderr)

        return 1
    except api.ConflictError:
        print(
            f"Model {identifier!r} is a semantic judge and was not deauthorized.",
            file=sys.stderr,
        )
        print(
            f"Remove it from the rotation first with: azathoth judge remove {identifier}",
            file=sys.stderr,
        )

        return 1
    except api.ApiError as exc:
        return _refused(exc)

    if removal.dependents:
        print(
            f"Warning: deauthorizing model {identifier!r} used by active production.",
            file=sys.stderr,
        )
        _print_dependents(removal.dependents)

    print(f"Deauthorized model {identifier}.")

    return 0


__all__ = [
    "authorize_model_on_remote",
    "deauthorize_model_on_remote",
    "list_models_on_remote",
    "list_portfolio_on_remote",
    "model_policy_on_remote",
    "show_model_on_remote",
]
