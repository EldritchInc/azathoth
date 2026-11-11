"""Current provider model commands for the Azathoth command-line application."""

import sys

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.service import current_author
from azathoth.providers import (
    ModelCapability,
    ModelMetadata,
    ModelModality,
    ModelPortfolioEntry,
    PolicyDeclaration,
)
from azathoth.sensitivity import (
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    PolicyAnswer,
)
from azathoth.workflows import (
    WorkflowModelUsageReport,
    model_usage_report,
)


def list_models() -> int:
    """List models currently available from configured providers."""

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    for model in runtime.models.models:
        print(f"{model.identifier}  {model.display_name}")

    return 0


def show_model(
    identifier: str,
) -> int:
    """Show one currently available provider model."""

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    model = runtime.models.get(identifier)

    if model is None:
        print(
            f"Model {identifier!r} is not currently available.",
            file=sys.stderr,
        )

        return 1

    _print_model(model)

    return 0


def list_portfolio_models() -> int:
    """List models authorized for organizational model selection."""

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    for entry in runtime.portfolio.entries:
        print(entry.identifier)

    return 0


def authorize_model(
    identifier: str,
    *,
    data_policy: DataPolicy = UNKNOWN_DATA_POLICY,
) -> int:
    """Authorize one currently available provider model.

    `data_policy` is what the operator declares the model's provider does
    with data it is sent; unknown unless declared (ADR 0123).
    """

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    model = runtime.models.get(identifier)

    if model is None:
        print(
            f"Model {identifier!r} is not currently available.",
            file=sys.stderr,
        )

        return 1

    if runtime.portfolio.get(identifier) is not None:
        print(
            f"Model {identifier!r} is already authorized.",
            file=sys.stderr,
        )

        return 1

    author = current_author()

    if author is None:
        return 1

    repository = repositories(configuration).portfolio

    repository.save(
        ModelPortfolioEntry(
            provider=model.provider,
            model=model.model,
            data_policy=data_policy,
        ),
        author=author,
    )

    print(f"Authorized model {identifier}.")

    return 0


def model_policy(
    identifier: str,
    *,
    retains_data: PolicyAnswer | None = None,
    trains_on_data: PolicyAnswer | None = None,
) -> int:
    """Show, or declare, what one authorized model's provider does with data (ADR 0123).

    An answer given replaces the one declared; an answer not given is kept.
    Given none, the policy is shown and nothing is written. Who declares it,
    and when, is recorded, and shown with it. Only durable state is read,
    so the runtime is never loaded and no provider credentials are needed.
    """

    configuration = CliRuntimeConfiguration.from_environment()
    repository = repositories(configuration).portfolio

    entry = repository.get(identifier)

    if entry is None:
        print(
            f"Model {identifier!r} is not authorized.",
            file=sys.stderr,
        )

        return 1

    if retains_data is None and trains_on_data is None:
        _print_data_policy(entry, repository.policy_declaration(identifier))

        return 0

    author = current_author()

    if author is None:
        return 1

    declared = repository.set_data_policy(
        identifier,
        DataPolicy(
            retains_data=(entry.data_policy.retains_data if retains_data is None else retains_data),
            trains_on_data=(
                entry.data_policy.trains_on_data if trains_on_data is None else trains_on_data
            ),
        ),
        author=author,
    )

    print(f"Declared the data policy of model {identifier}.")

    _print_data_policy(declared, repository.policy_declaration(identifier))

    return 0


def _print_data_policy(
    entry: ModelPortfolioEntry,
    declaration: PolicyDeclaration | None,
) -> None:
    """Render what one portfolio entry declares its provider does with data, and who declared it.

    A policy never declared names no declaration; one declared without a
    recorded author names its author as unknown.
    """

    policy = entry.data_policy

    print(f"Retains Data: {policy.retains_data.value}")
    print(f"Trains On Data: {policy.trains_on_data.value}")
    print(f"Restricted Input: {'allowed' if policy.private else 'refused'}")

    if declaration is not None:
        author = declaration.author

        print(f"Declared By: {'unknown' if author is None else author}")
        print(f"Declared At: {declaration.declared_at.isoformat()}")


def deauthorize_model(
    identifier: str,
    *,
    force: bool = False,
) -> int:
    """Remove one model from organizational authorization.

    Deauthorization is refused while active production holds the model as a
    primary or approved substitute, because those workflows would lose a model
    they are pinned to. Forcing proceeds anyway and reports the dependents.

    Deauthorization is always refused, even when forced, while the model is in
    the semantic judge rotation: judges must be authorized, so the judge must
    be removed from the rotation first.
    """

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    if runtime.portfolio.get(identifier) is None:
        print(
            f"Model {identifier!r} is not authorized.",
            file=sys.stderr,
        )

        return 1

    if repositories(configuration).judges.get(identifier) is not None:
        print(
            f"Model {identifier!r} is a semantic judge and was not deauthorized.",
            file=sys.stderr,
        )

        print(
            f"Remove it from the rotation first with: azathoth judge remove {identifier}",
            file=sys.stderr,
        )

        return 1

    report = model_usage_report(
        identifier,
        specifications=(),
        production_states=repositories(configuration).production_states.states(),
        runs=(),
    )

    if report.in_production:
        if not force:
            print(
                f"Model {identifier!r} is used by active production and was not deauthorized.",
                file=sys.stderr,
            )

            _print_production_dependents(report)

            print(
                "Use --force to deauthorize anyway.",
                file=sys.stderr,
            )

            return 1

        print(
            f"Warning: deauthorizing model {identifier!r} used by active production.",
            file=sys.stderr,
        )

        _print_production_dependents(report)

    repository = repositories(configuration).portfolio

    repository.delete(identifier)

    print(f"Deauthorized model {identifier}.")

    return 0


def _print_production_dependents(
    report: WorkflowModelUsageReport,
) -> None:
    """Report production workflows depending on one model."""

    for entry in report.production_workflows:
        roles = ", ".join(f"{usage.role.value} step {usage.step_id}" for usage in entry.production)

        print(
            f"  {entry.workflow.name} ({entry.workflow.id}): {roles}",
            file=sys.stderr,
        )


def _print_model(
    model: ModelMetadata,
) -> None:
    """Render one current model using provider-neutral metadata."""

    print(f"ID: {model.identifier}")
    print(f"Provider: {model.provider}")
    print(f"Model: {model.model}")
    print(f"Name: {model.display_name}")

    print(f"Input Modalities: {_render_values(model.input_modalities)}")

    print(f"Output Modalities: {_render_values(model.output_modalities)}")

    print(f"Capabilities: {_render_values(model.capabilities)}")

    print(f"Context Window: {_render_optional_integer(model.context_window_tokens)}")

    print(f"Maximum Output Tokens: {_render_optional_integer(model.maximum_output_tokens)}")

    if model.pricing is None:
        print("Input Price: unknown")
        print("Output Price: unknown")
        return

    print(f"Input Price: ${model.pricing.input_usd_per_million_tokens:.6f} per million tokens")

    print(f"Output Price: ${model.pricing.output_usd_per_million_tokens:.6f} per million tokens")


def _render_values(
    values: frozenset[ModelCapability] | frozenset[ModelModality],
) -> str:
    """Render deterministic model enum values."""

    if not values:
        return "none"

    return ", ".join(sorted(value.value for value in values))


def _render_optional_integer(
    value: int | None,
) -> str:
    """Render an optional integer model property."""

    if value is None:
        return "unknown"

    return str(value)
