"""Tests for the records a push carries, each checked against its digests (ADR 0124)."""

from uuid import UUID

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.inputs import ContentRef
from azathoth.remote import (
    PROTOCOL_VERSION,
    ContentRecord,
    MissingRequest,
    MissingResponse,
    PushBundle,
    RevisionRecord,
    document_sensitivity,
)
from azathoth.revisions import (
    Author,
    Lineage,
    RevisionKind,
    content_digest,
    json_digest,
    revision_digest,
)
from azathoth.sensitivity import Sensitivity
from azathoth.tools import ToolDocument, ToolRequirement
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.tools.test_catalog import create_tool_definition

WORKFLOW_ID = UUID("4e700000-0000-4000-8000-000000000001")

TOOL_ID = UUID("4e700000-0000-4000-8000-000000000002")

BENCHMARK_ID = UUID("4e700000-0000-4000-8000-000000000003")

STEP_ID = UUID("4e700000-0000-4000-8000-000000000011")

WORKFLOW = Lineage(kind=RevisionKind.WORKFLOW, id=WORKFLOW_ID)

TOOL = Lineage(kind=RevisionKind.TOOL, id=TOOL_ID, version="1.0.0")

BENCHMARK = Lineage(kind=RevisionKind.BENCHMARK, id=BENCHMARK_ID)

ANSWER = ExpectedOutcome(
    description="Answers.",
    value="answer",
    comparison=OutcomeComparison.EXACT,
)

CHART = ContentRef(digest="c" * 64, media_type="application/pdf", size_bytes=4)


def specification(
    name: str = "count",
) -> WorkflowSpecification:
    return WorkflowSpecification(
        metadata=WorkflowMetadata(id=WORKFLOW_ID, name=name, description="Count words."),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(name="word_count", version="1.0.0"),
                ),
            ),
        ),
    )


def dataset(
    *labels: Sensitivity | None,
) -> BenchmarkDataset:
    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="claims",
        description="Claims.",
        cases=tuple(
            BenchmarkCase(
                id=UUID(int=BENCHMARK_ID.int + index + 1),
                input=f"claim {index}",
                expected=ANSWER,
                sensitivity=label,
            )
            for index, label in enumerate(labels)
        ),
    )


def record(
    lineage: Lineage,
    document: BaseModel,
    *,
    parent: RevisionRecord | None = None,
    author: Author | None = None,
) -> RevisionRecord:
    """Return the record of one revision of a document, built on a parent or first."""

    digest = content_digest(document)
    parent_digest = None if parent is None else parent.revision_digest

    return RevisionRecord(
        lineage=lineage,
        revision_digest=revision_digest(
            lineage,
            content_digest=digest,
            parent_digest=parent_digest,
        ),
        parent_digest=parent_digest,
        content_digest=digest,
        author=author,
        document=document.model_dump(mode="json"),
    )


def tampered(
    original: RevisionRecord,
    **changes: JsonValue,
) -> None:
    """Validate a record's JSON with some fields changed, so it can be refused."""

    RevisionRecord.model_validate({**original.model_dump(mode="json"), **changes})


# Revisions


def test_a_record_of_each_kind_is_accepted() -> None:
    first = record(WORKFLOW, specification(), author=Author(name="Eris"))
    second = record(WORKFLOW, specification("tally"), parent=first)

    assert second.parent_digest == first.revision_digest
    assert RevisionRecord.model_validate_json(first.model_dump_json()) == first
    assert record(TOOL, ToolDocument(definition=create_tool_definition(tool_id=TOOL_ID)))
    assert record(BENCHMARK, dataset())


def test_a_document_of_another_lineage_is_refused() -> None:
    original = record(WORKFLOW, specification())
    other = Lineage(kind=RevisionKind.WORKFLOW, id=TOOL_ID)

    with pytest.raises(ValidationError) as caught:
        tampered(original, lineage=other.model_dump(mode="json"))

    assert (
        f"Revision {original.revision_digest} holds a document that is not one of "
        f"workflow {TOOL_ID}'s." in str(caught.value)
    )


@pytest.mark.parametrize(
    "document",
    [
        "a workflow",
        {"metadata": {"id": 412}},
        {"metadata": {"id": "not a UUID"}},
        {"metadata": "none"},
    ],
    ids=["text", "numbered", "unparsed", "no-metadata"],
)
def test_a_document_naming_no_lineage_is_refused(
    document: JsonValue,
) -> None:
    with pytest.raises(ValidationError, match="holds a document that is not one of"):
        tampered(record(WORKFLOW, specification()), document=document)


def test_a_tool_document_of_another_version_is_refused() -> None:
    original = record(TOOL, ToolDocument(definition=create_tool_definition(tool_id=TOOL_ID)))

    with pytest.raises(ValidationError, match="holds a document that is not one of"):
        tampered(original, lineage={"kind": "tool", "id": str(TOOL_ID), "version": "2.0.0"})


def test_a_benchmark_of_another_id_is_refused() -> None:
    original = record(BENCHMARK, dataset())

    with pytest.raises(ValidationError, match="holds a document that is not one of"):
        tampered(original, lineage={"kind": "benchmark", "id": str(WORKFLOW_ID)})


def test_a_document_that_is_not_its_content_is_refused() -> None:
    original = record(WORKFLOW, specification())
    changed = specification("tally")

    with pytest.raises(ValidationError) as caught:
        tampered(original, document=changed.model_dump(mode="json"))

    assert (
        f"Revision {original.revision_digest} of workflow {WORKFLOW_ID} holds content "
        f"{content_digest(changed)}, not its content digest {original.content_digest}."
    ) in str(caught.value)


def test_a_revision_digest_that_is_not_its_identity_is_refused() -> None:
    original = record(WORKFLOW, specification())
    parent = "d" * 64

    with pytest.raises(ValidationError) as caught:
        tampered(original, parent_digest=parent)

    computed = revision_digest(
        WORKFLOW,
        content_digest=original.content_digest,
        parent_digest=parent,
    )

    assert (
        f"Revision {original.revision_digest} of workflow {WORKFLOW_ID} is not the digest of its "
        f"lineage, content and parent, which is {computed}."
    ) in str(caught.value)


# Labels


def test_a_benchmark_is_as_sensitive_as_its_most_sensitive_case() -> None:
    assert record(BENCHMARK, dataset()).sensitivity is Sensitivity.INTERNAL
    assert record(BENCHMARK, dataset(None, Sensitivity.PUBLIC)).sensitivity is (
        Sensitivity.INTERNAL
    )
    assert record(BENCHMARK, dataset(Sensitivity.PUBLIC)).sensitivity is Sensitivity.PUBLIC
    assert record(
        BENCHMARK, dataset(Sensitivity.PUBLIC, Sensitivity.RESTRICTED, None)
    ).sensitivity is (Sensitivity.RESTRICTED)


def test_workflows_and_tools_hold_no_data() -> None:
    assert record(WORKFLOW, specification()).sensitivity is Sensitivity.INTERNAL
    assert document_sensitivity(TOOL, {"cases": [{"sensitivity": "restricted"}]}) is (
        Sensitivity.INTERNAL
    )


@pytest.mark.parametrize("label", ["secret", 3, ["restricted"]], ids=["unknown", "number", "list"])
def test_a_case_naming_an_unknown_label_is_refused(
    label: JsonValue,
) -> None:
    with pytest.raises(ValueError) as caught:
        document_sensitivity(BENCHMARK, {"cases": [{}, {"sensitivity": label}]})

    assert str(caught.value) == (
        f"A case of benchmark {BENCHMARK_ID} is labelled {label!r}, which is not a sensitivity "
        "label."
    )


def test_a_record_holding_an_unknown_label_is_refused() -> None:
    document = dataset(Sensitivity.RESTRICTED).model_dump(mode="json")
    document["cases"][0]["sensitivity"] = "secret"
    digest = json_digest(document)

    with pytest.raises(ValidationError, match="labelled 'secret', which is not a sensitivity"):
        RevisionRecord(
            lineage=BENCHMARK,
            revision_digest=revision_digest(BENCHMARK, content_digest=digest, parent_digest=None),
            parent_digest=None,
            content_digest=digest,
            document=document,
        )


def test_a_document_without_cases_is_internal() -> None:
    assert document_sensitivity(BENCHMARK, {"cases": "none"}) is Sensitivity.INTERNAL
    assert document_sensitivity(BENCHMARK, "a benchmark") is Sensitivity.INTERNAL


# Bundles


def chart_case_dataset() -> BenchmarkDataset:
    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="charts",
        description="Charts.",
        cases=(
            BenchmarkCase(
                input=CHART.to_value(),
                expected=ANSWER,
                sensitivity=Sensitivity.RESTRICTED,
            ),
        ),
    )


def test_a_bundle_carries_lineages_in_order_and_their_content() -> None:
    first = record(WORKFLOW, specification())
    second = record(WORKFLOW, specification("tally"), parent=first)
    tool = record(TOOL, ToolDocument(definition=create_tool_definition(tool_id=TOOL_ID)))
    held = ContentRecord(content=CHART, sensitivity=Sensitivity.RESTRICTED)

    bundle = PushBundle(revisions=(first, tool, second), content=(held,))

    assert bundle.protocol == PROTOCOL_VERSION
    assert held.digest == CHART.digest
    assert PushBundle.model_validate_json(bundle.model_dump_json()) == bundle


def test_a_lineages_first_revision_in_a_bundle_may_build_on_one_the_remote_holds() -> None:
    first = record(WORKFLOW, specification())
    second = record(WORKFLOW, specification("tally"), parent=first)

    assert PushBundle(revisions=(second,)).revisions == (second,)


def test_a_child_before_its_parent_is_refused() -> None:
    first = record(WORKFLOW, specification())
    second = record(WORKFLOW, specification("tally"), parent=first)
    third = record(WORKFLOW, specification("sum"), parent=second)

    with pytest.raises(ValidationError) as caught:
        PushBundle(revisions=(first, third, second))

    assert (
        f"Revision {third.revision_digest} of workflow {WORKFLOW_ID} does not build on the "
        f"revision before it in the push, {first.revision_digest}."
    ) in str(caught.value)


def test_a_repeated_revision_is_refused() -> None:
    first = record(WORKFLOW, specification())

    with pytest.raises(ValidationError) as caught:
        PushBundle(revisions=(first, first))

    assert f"Revision {first.revision_digest} appears twice in the push." in str(caught.value)


def test_repeated_content_is_refused() -> None:
    held = ContentRecord(content=CHART)

    with pytest.raises(ValidationError) as caught:
        PushBundle(content=(held, held.model_copy(update={"sensitivity": Sensitivity.PUBLIC})))

    assert f"Content {CHART.digest} appears twice in the push." in str(caught.value)


def test_a_bundle_is_as_sensitive_as_anything_it_carries() -> None:
    workflow = record(WORKFLOW, specification())
    public = record(BENCHMARK, dataset(Sensitivity.PUBLIC))

    assert PushBundle().sensitivity is Sensitivity.INTERNAL
    assert PushBundle(revisions=(public,)).sensitivity is Sensitivity.PUBLIC
    assert PushBundle(revisions=(workflow,)).sensitivity is Sensitivity.INTERNAL
    assert (
        PushBundle(
            revisions=(public,),
            content=(ContentRecord(content=CHART, sensitivity=Sensitivity.RESTRICTED),),
        ).sensitivity
        is Sensitivity.RESTRICTED
    )
    assert (
        PushBundle(revisions=(record(BENCHMARK, chart_case_dataset()),)).sensitivity
        is Sensitivity.RESTRICTED
    )


def test_content_is_internal_unless_labelled() -> None:
    assert ContentRecord(content=CHART).sensitivity is Sensitivity.INTERNAL


# Have and want


def test_the_remote_answers_with_what_it_lacks_in_the_order_offered() -> None:
    request = MissingRequest(revisions=("a" * 64, "b" * 64, "c" * 64), content=("d" * 64, "e" * 64))

    assert request.missing(
        held_revisions={"b" * 64},
        held_content={"d" * 64, "e" * 64},
    ) == MissingResponse(revisions=("a" * 64, "c" * 64), content=())


def test_digests_offered_must_be_digests() -> None:
    with pytest.raises(ValidationError):
        MissingRequest(revisions=("not a digest",))

    with pytest.raises(ValidationError):
        MissingResponse(content=("A" * 64,))
