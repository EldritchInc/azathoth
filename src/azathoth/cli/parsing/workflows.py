"""Workflow command-line parser construction."""

from __future__ import annotations

from argparse import SUPPRESS, ArgumentParser, _MutuallyExclusiveGroup, _SubParsersAction
from pathlib import Path
from uuid import UUID

from azathoth.cli.output_format import (
    DEFAULT_WORKFLOW_OUTPUT_FORMAT,
    WorkflowOutputFormat,
)
from azathoth.cli.parsing.common import (
    json_value,
    media_type,
    positive_integer,
)

WORKFLOW_COMMAND = "workflow"

WORKFLOW_ACTION_ATTRIBUTE = "workflow_action"

WORKFLOW_EXPERIMENTS_ACTION = "experiments"
WORKFLOW_EXPORT_ACTION = "export"
WORKFLOW_HISTORY_ACTION = "history"
WORKFLOW_IMPORT_ACTION = "import"
WORKFLOW_INVOCATIONS_ACTION = "invocations"
WORKFLOW_INVOKE_ACTION = "invoke"
WORKFLOW_LIST_ACTION = "list"
WORKFLOW_OPTIMIZE_ACTION = "optimize"
WORKFLOW_PRODUCTION_ACTION = "production"
WORKFLOW_PROMOTE_ACTION = "promote"
WORKFLOW_REVISIONS_ACTION = "revisions"
WORKFLOW_RUN_ACTION = "run"
WORKFLOW_RUNS_ACTION = "runs"
WORKFLOW_SHOW_ACTION = "show"

WORKFLOW_BENCHMARK_ID_ATTRIBUTE = "workflow_benchmark_id"
WORKFLOW_DOCUMENT_ATTRIBUTE = "workflow_document"
WORKFLOW_EXPERIMENT_LIMIT_ATTRIBUTE = "workflow_experiment_limit"
WORKFLOW_PROMOTE_EXPERIMENT_ATTRIBUTE = "workflow_promote_experiment"
WORKFLOW_HISTORY_LIMIT_ATTRIBUTE = "workflow_history_limit"
WORKFLOW_ID_ATTRIBUTE = "workflow_id"
WORKFLOW_INPUT_ATTRIBUTE = "workflow_input"
WORKFLOW_INPUT_FILE_ATTRIBUTE = "workflow_input_file"
WORKFLOW_INPUT_MEDIA_TYPE_ATTRIBUTE = "workflow_input_media_type"
WORKFLOW_INVOCATION_LIMIT_ATTRIBUTE = "workflow_invocation_limit"
WORKFLOW_OUTPUT_ATTRIBUTE = "workflow_output"
WORKFLOW_REVISION_LIMIT_ATTRIBUTE = "workflow_revision_limit"
WORKFLOW_RUN_LIMIT_ATTRIBUTE = "workflow_run_limit"
WORKFLOW_SPECIFICATION_REVISION_ATTRIBUTE = "workflow_specification_revision"

TARGET_LATENCY_ATTRIBUTE = "target_latency_seconds"
TARGET_COST_ATTRIBUTE = "target_cost_usd"
GENERATIONS_ATTRIBUTE = "generations"


def add_workflow_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add workflow commands to the Azathoth parser."""

    workflow_parser = commands.add_parser(
        WORKFLOW_COMMAND,
        help="Inspect and operate configured workflows.",
    )

    workflow_actions = workflow_parser.add_subparsers(
        dest=WORKFLOW_ACTION_ATTRIBUTE,
    )

    workflow_actions.add_parser(
        WORKFLOW_LIST_ACTION,
        help="List configured workflows.",
    )

    workflow_show_parser = workflow_actions.add_parser(
        WORKFLOW_SHOW_ACTION,
        help="Show one configured workflow.",
    )

    workflow_show_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to inspect.",
    )

    workflow_show_parser.add_argument(
        "--revision",
        dest=WORKFLOW_SPECIFICATION_REVISION_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="NUMBER",
        help="Imported revision to inspect. Defaults to the latest.",
    )

    workflow_history_parser = workflow_actions.add_parser(
        WORKFLOW_HISTORY_ACTION,
        help="List imported revisions of one workflow, newest first.",
    )

    workflow_history_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID whose imported revisions to list.",
    )

    workflow_history_parser.add_argument(
        "--limit",
        dest=WORKFLOW_HISTORY_LIMIT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="COUNT",
        help="Maximum number of most recent revisions to list.",
    )

    workflow_export_parser = workflow_actions.add_parser(
        WORKFLOW_EXPORT_ACTION,
        help="Print one imported workflow revision as an importable JSON document.",
    )

    workflow_export_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to export.",
    )

    workflow_export_parser.add_argument(
        "--revision",
        dest=WORKFLOW_SPECIFICATION_REVISION_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="NUMBER",
        help="Imported revision to export. Defaults to the latest.",
    )

    workflow_import_parser = workflow_actions.add_parser(
        WORKFLOW_IMPORT_ACTION,
        help="Import a workflow JSON document.",
    )

    workflow_import_parser.add_argument(
        WORKFLOW_DOCUMENT_ATTRIBUTE,
        type=Path,
        metavar="FILE",
        help="JSON workflow document to import.",
    )

    workflow_run_parser = workflow_actions.add_parser(
        WORKFLOW_RUN_ACTION,
        help="Execute one configured workflow.",
    )

    workflow_run_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to execute.",
    )

    workflow_run_input = workflow_run_parser.add_mutually_exclusive_group()

    workflow_run_input.add_argument(
        "--input",
        dest=WORKFLOW_INPUT_ATTRIBUTE,
        default=SUPPRESS,
        type=json_value,
        metavar="JSON",
        help="Workflow input as JSON. Without any input the run starts with an empty context.",
    )

    _add_input_file_arguments(workflow_run_parser, workflow_run_input)

    _add_output_argument(workflow_run_parser)

    workflow_invoke_parser = workflow_actions.add_parser(
        WORKFLOW_INVOKE_ACTION,
        help="Invoke one active production workflow.",
    )

    workflow_invoke_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Production workflow UUID to invoke.",
    )

    workflow_invoke_input = workflow_invoke_parser.add_mutually_exclusive_group(
        required=True,
    )

    workflow_invoke_input.add_argument(
        "--input",
        dest=WORKFLOW_INPUT_ATTRIBUTE,
        default=SUPPRESS,
        type=json_value,
        metavar="JSON",
        help="Production workflow input as JSON.",
    )

    _add_input_file_arguments(workflow_invoke_parser, workflow_invoke_input)

    _add_output_argument(workflow_invoke_parser)

    workflow_optimize_parser = workflow_actions.add_parser(
        WORKFLOW_OPTIMIZE_ACTION,
        help="Empirically optimize one configured workflow.",
    )

    workflow_optimize_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to optimize.",
    )

    workflow_optimize_parser.add_argument(
        "--benchmark",
        dest=WORKFLOW_BENCHMARK_ID_ATTRIBUTE,
        required=True,
        type=UUID,
        metavar="BENCHMARK_ID",
        help="Benchmark UUID whose cases judge every candidate.",
    )

    workflow_optimize_parser.add_argument(
        "--target-latency",
        dest=TARGET_LATENCY_ATTRIBUTE,
        required=True,
        type=float,
        metavar="SECONDS",
        help="Target workflow latency in seconds.",
    )

    workflow_optimize_parser.add_argument(
        "--target-cost",
        dest=TARGET_COST_ATTRIBUTE,
        required=True,
        type=float,
        metavar="USD",
        help="Target workflow execution cost in USD.",
    )

    workflow_optimize_parser.add_argument(
        "--generations",
        dest=GENERATIONS_ATTRIBUTE,
        type=int,
        default=1,
        metavar="COUNT",
        help="Number of empirical optimization generations.",
    )

    workflow_promote_parser = workflow_actions.add_parser(
        WORKFLOW_PROMOTE_ACTION,
        help="Promote one configured workflow to active production.",
    )

    workflow_promote_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID to promote.",
    )

    workflow_promote_parser.add_argument(
        "--experiment",
        dest=WORKFLOW_PROMOTE_EXPERIMENT_ATTRIBUTE,
        type=UUID,
        default=None,
        metavar="EXPERIMENT_ID",
        help="Promote this optimization experiment's winner instead of the configured candidate.",
    )

    workflow_production_parser = workflow_actions.add_parser(
        WORKFLOW_PRODUCTION_ACTION,
        help="Show the active production configuration of one workflow.",
    )

    workflow_production_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID whose production configuration to show.",
    )

    workflow_revisions_parser = workflow_actions.add_parser(
        WORKFLOW_REVISIONS_ACTION,
        help="List production revisions of one workflow, newest first.",
    )

    workflow_revisions_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID whose production revisions to list.",
    )

    workflow_revisions_parser.add_argument(
        "--limit",
        dest=WORKFLOW_REVISION_LIMIT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="COUNT",
        help="Maximum number of most recent revisions to list.",
    )

    workflow_invocations_parser = workflow_actions.add_parser(
        WORKFLOW_INVOCATIONS_ACTION,
        help="List production invocations of one workflow, newest first.",
    )

    workflow_invocations_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID whose production invocations to list.",
    )

    workflow_invocations_parser.add_argument(
        "--limit",
        dest=WORKFLOW_INVOCATION_LIMIT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="COUNT",
        help="Maximum number of most recent invocations to list.",
    )

    workflow_experiments_parser = workflow_actions.add_parser(
        WORKFLOW_EXPERIMENTS_ACTION,
        help="List persisted experiments of one workflow, newest first.",
    )

    workflow_experiments_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID whose experiments to list.",
    )

    workflow_experiments_parser.add_argument(
        "--limit",
        dest=WORKFLOW_EXPERIMENT_LIMIT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="COUNT",
        help="Maximum number of most recent experiments to list.",
    )

    workflow_runs_parser = workflow_actions.add_parser(
        WORKFLOW_RUNS_ACTION,
        help="List persisted runs of one workflow, newest first.",
    )

    workflow_runs_parser.add_argument(
        WORKFLOW_ID_ATTRIBUTE,
        type=UUID,
        metavar="WORKFLOW_ID",
        help="Workflow UUID whose runs to list.",
    )

    workflow_runs_parser.add_argument(
        "--limit",
        dest=WORKFLOW_RUN_LIMIT_ATTRIBUTE,
        type=positive_integer,
        default=None,
        metavar="COUNT",
        help="Maximum number of most recent runs to list.",
    )


def _add_input_file_arguments(
    parser: ArgumentParser,
    inputs: _MutuallyExclusiveGroup,
) -> None:
    """Add the file input options of a workflow execution command (ADR 0096).

    `--input-file` is one of the command's mutually exclusive inputs.
    """

    inputs.add_argument(
        "--input-file",
        dest=WORKFLOW_INPUT_FILE_ATTRIBUTE,
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Workflow input read from a JSON or text file. Its media type comes "
            "from its extension unless --media-type gives it."
        ),
    )

    parser.add_argument(
        "--media-type",
        dest=WORKFLOW_INPUT_MEDIA_TYPE_ATTRIBUTE,
        type=media_type,
        default=None,
        metavar="TYPE",
        help="Media type of --input-file: application/json or a text/* type.",
    )


def _add_output_argument(
    parser: ArgumentParser,
) -> None:
    """Add the output format option of a workflow execution command."""

    parser.add_argument(
        "--output",
        dest=WORKFLOW_OUTPUT_ATTRIBUTE,
        choices=tuple(output_format.value for output_format in WorkflowOutputFormat),
        default=DEFAULT_WORKFLOW_OUTPUT_FORMAT.value,
        help=(
            "Output format: jsonl streams step records and a terminal record "
            "(default), text prints the human-readable report, result prints "
            "only the result as JSON."
        ),
    )
