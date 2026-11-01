"""Tests for the standard text tools: chunk_text, join_text and render_template."""

import pytest
from pydantic import JsonValue

from tests.standard.harness import (
    run_standard_tool,
    standard_document,
    standard_tool_failure,
)

ESSAY = (
    "The keeper climbed the stairs at dusk. The lamp was cold!\n"
    "She lit it anyway.\n\n"
    "Below, the sea turned over in its sleep. Nobody in the village asked why "
    "the water had gone so still, or why the gulls had stopped calling.\n\n"
    "« Été » came late that year — and left early."
)

UNBROKEN = "x" * 95


def chunks_of(
    inputs: dict[str, JsonValue],
) -> list[str]:
    """Run chunk_text and return its chunks."""

    output = run_standard_tool("chunk_text", inputs)
    chunks = output["chunks"]

    assert isinstance(chunks, list)
    assert all(isinstance(chunk, str) for chunk in chunks)

    return [chunk for chunk in chunks if isinstance(chunk, str)]


# chunk_text


@pytest.mark.parametrize("text", [ESSAY, UNBROKEN], ids=["essay", "unbroken"])
@pytest.mark.parametrize("size", [1, 7, 20, 50, 80, 1000])
def test_chunk_text_without_overlap_splits_the_text_exactly(
    text: str,
    size: int,
) -> None:
    chunks = chunks_of({"text": text, "max_characters": size})

    assert "".join(chunks) == text
    assert all(1 <= len(chunk) <= size for chunk in chunks)


@pytest.mark.parametrize("size", [20, 50])
@pytest.mark.parametrize("overlap", [1, 5, 19])
def test_chunk_text_overlaps_each_chunk_with_the_one_before(
    size: int,
    overlap: int,
) -> None:
    chunks = chunks_of({"text": ESSAY, "max_characters": size, "overlap_characters": overlap})

    assert all(1 <= len(chunk) <= size for chunk in chunks)

    start = 0

    for index, chunk in enumerate(chunks):
        assert ESSAY[start : start + len(chunk)] == chunk, index

        start = max(start + len(chunk) - overlap, start + 1)

    assert start + overlap >= len(ESSAY)


def test_chunk_text_prefers_a_paragraph_break() -> None:
    assert chunks_of({"text": ESSAY, "max_characters": 100})[0] == (
        "The keeper climbed the stairs at dusk. The lamp was cold!\nShe lit it anyway.\n\n"
    )


def test_chunk_text_falls_back_to_a_line_break() -> None:
    assert chunks_of({"text": ESSAY, "max_characters": 70})[0] == (
        "The keeper climbed the stairs at dusk. The lamp was cold!\n"
    )


def test_chunk_text_falls_back_to_a_sentence_end() -> None:
    assert chunks_of({"text": ESSAY, "max_characters": 50})[0] == (
        "The keeper climbed the stairs at dusk. "
    )


def test_chunk_text_falls_back_to_whitespace() -> None:
    assert chunks_of({"text": ESSAY, "max_characters": 30})[0] == "The keeper climbed the stairs "


def test_chunk_text_ignores_a_boundary_in_the_first_half_of_a_chunk() -> None:
    assert chunks_of({"text": "Hi. " + "y" * 40, "max_characters": 20}) == [
        "Hi. " + "y" * 16,
        "y" * 20,
        "y" * 4,
    ]


def test_chunk_text_cuts_unbroken_text_at_the_limit() -> None:
    assert chunks_of({"text": "abcdefghij", "max_characters": 4}) == ["abcd", "efgh", "ij"]


def test_chunk_text_counts_characters_not_bytes() -> None:
    assert chunks_of({"text": "ééééé", "max_characters": 2}) == ["éé", "éé", "é"]


def test_chunk_text_overlaps_by_characters() -> None:
    assert chunks_of({"text": "abcdefghij", "max_characters": 4, "overlap_characters": 1}) == [
        "abcd",
        "defg",
        "ghij",
    ]


def test_chunk_text_keeps_a_short_text_whole() -> None:
    assert chunks_of({"text": "Short.", "max_characters": 6}) == ["Short."]


def test_chunk_text_of_empty_text_is_no_chunks() -> None:
    assert chunks_of({"text": "", "max_characters": 5}) == []


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param(
            {"text": 1, "max_characters": 5},
            "chunk_text needs 'text' to be a string.",
            id="text-not-a-string",
        ),
        pytest.param(
            {"text": "x", "max_characters": 0},
            "chunk_text needs 'max_characters' to be a whole number of at least 1.",
            id="zero-size",
        ),
        pytest.param(
            {"text": "x", "max_characters": 2.5},
            "chunk_text needs 'max_characters' to be a whole number of at least 1.",
            id="fractional-size",
        ),
        pytest.param(
            {"text": "x", "max_characters": True},
            "chunk_text needs 'max_characters' to be a whole number of at least 1.",
            id="boolean-size",
        ),
        pytest.param(
            {"text": "x", "max_characters": 5, "overlap_characters": 5},
            "chunk_text needs 'overlap_characters' to be a whole number from 0 to one less "
            "than 'max_characters'.",
            id="overlap-too-large",
        ),
        pytest.param(
            {"text": "x", "max_characters": 5, "overlap_characters": -1},
            "chunk_text needs 'overlap_characters' to be a whole number from 0 to one less "
            "than 'max_characters'.",
            id="negative-overlap",
        ),
        pytest.param(
            {"max_characters": 5},
            "chunk_text needs the input 'text'.",
            id="no-text",
        ),
        pytest.param(
            {"text": "x"},
            "chunk_text needs the input 'max_characters'.",
            id="no-size",
        ),
        pytest.param(
            {"text": "x", "max_characters": 5, "max_tokens": 5},
            "chunk_text does not take the input 'max_tokens'.",
            id="unknown-input",
        ),
    ],
)
def test_chunk_text_rejects_unusable_inputs(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("chunk_text", inputs) == (2, message)


# join_text


def test_join_text_joins_strings_with_two_line_breaks_by_default() -> None:
    assert run_standard_tool("join_text", {"items": ["One.", "Two."]}) == {"text": "One.\n\nTwo."}


def test_join_text_uses_the_separator_it_is_given() -> None:
    assert run_standard_tool("join_text", {"items": ["a", "b", "c"], "separator": ", "}) == {
        "text": "a, b, c"
    }


def test_join_text_rejoins_what_chunk_text_split() -> None:
    chunks = chunks_of({"text": ESSAY, "max_characters": 40})

    assert run_standard_tool("join_text", {"items": list(chunks), "separator": ""}) == {
        "text": ESSAY
    }


def test_join_text_of_no_items_is_empty() -> None:
    assert run_standard_tool("join_text", {"items": []}) == {"text": ""}


def test_join_text_renders_each_object_through_the_item_template() -> None:
    assert run_standard_tool(
        "join_text",
        {
            "items": [
                {"number": 1, "title": "Dusk", "text": "The lamp was cold."},
                {"number": 2, "title": "Été", "text": "The sea slept."},
            ],
            "item_template": "## Chapter {number}: {title}\n\n{text}",
        },
    ) == {
        "text": ("## Chapter 1: Dusk\n\nThe lamp was cold.\n\n## Chapter 2: Été\n\nThe sea slept.")
    }


def test_join_text_renders_non_string_fields_as_compact_json() -> None:
    assert run_standard_tool(
        "join_text",
        {
            "items": [{"tags": ["a", "b"], "meta": {"n": 1}, "none": None}],
            "item_template": ("{tags} {meta} {none} {{literal}}"),
        },
    ) == {"text": '["a","b"] {"n":1} null {literal}'}


@pytest.mark.parametrize(
    ("inputs", "status", "message"),
    [
        pytest.param(
            {"items": [{"number": 1}, {"title": "x"}], "item_template": "{number}"},
            1,
            "join_text found no value for {number} in item $[1].",
            id="missing-field",
        ),
        pytest.param(
            {"items": ["a", {"x": 1}]},
            2,
            "join_text joins strings, or objects through an item_template; item $[1] is an object.",
            id="object-without-template",
        ),
        pytest.param(
            {"items": ["a", None]},
            2,
            "join_text joins strings, or objects through an item_template; item $[1] is null.",
            id="null-without-template",
        ),
        pytest.param(
            {"items": [{"n": 1}, "s"], "item_template": "{n}"},
            2,
            "join_text fills its item_template from objects; item $[1] is a string.",
            id="string-with-template",
        ),
        pytest.param(
            {"items": [{"n": 1}], "item_template": "{n.x}"},
            2,
            "join_text allows only plain {name} placeholders; {n.x} is not one.",
            id="dotted-placeholder",
        ),
        pytest.param(
            {"items": [{"n": 1}], "item_template": "{n"},
            2,
            "join_text could not read the item template: expected '}' before end of string.",
            id="unclosed-brace",
        ),
        pytest.param(
            {"items": "a"},
            2,
            "join_text needs 'items' to be an array.",
            id="items-not-an-array",
        ),
        pytest.param(
            {"items": [], "separator": None},
            2,
            "join_text needs 'separator' to be a string.",
            id="separator-not-a-string",
        ),
        pytest.param(
            {"items": [], "item_template": None},
            2,
            "join_text needs 'item_template' to be a string.",
            id="null-template",
        ),
        pytest.param({}, 2, "join_text needs the input 'items'.", id="no-items"),
        pytest.param(
            {"items": [], "template": "{x}"},
            2,
            "join_text does not take the input 'template'.",
            id="unknown-input",
        ),
    ],
)
def test_join_text_fails_explicitly(
    inputs: dict[str, JsonValue],
    status: int,
    message: str,
) -> None:
    assert standard_tool_failure("join_text", inputs) == (status, message)


# render_template


def test_render_template_fills_placeholders_from_its_inputs() -> None:
    assert run_standard_tool(
        "render_template",
        {"template": "# {title}\n\n{chapters}\n", "title": "The Keeper", "chapters": "..."},
    ) == {"text": "# The Keeper\n\n...\n"}


def test_render_template_renders_values_the_way_prompts_do() -> None:
    assert run_standard_tool(
        "render_template",
        {
            "template": "{story} | {count} | {ok} | {nothing} | {text}",
            "story": {"title": "Le phare", "tags": ["été"]},
            "count": 3,
            "ok": True,
            "nothing": None,
            "text": "plain",
        },
    ) == {"text": '{"title":"Le phare","tags":["été"]} | 3 | true | null | plain'}


def test_render_template_keeps_doubled_braces_literal_and_ignores_unused_inputs() -> None:
    assert run_standard_tool(
        "render_template",
        {"template": '{{"verdict": "{verdict}"}}', "verdict": "pass", "unused": 1},
    ) == {"text": '{"verdict": "pass"}'}


def test_render_template_repeats_a_placeholder() -> None:
    assert run_standard_tool("render_template", {"template": "{a}{a}{a}", "a": "x"}) == {
        "text": "xxx"
    }


def test_render_template_without_placeholders_returns_the_template() -> None:
    assert run_standard_tool("render_template", {"template": "No placeholders."}) == {
        "text": "No placeholders."
    }


@pytest.mark.parametrize(
    "template",
    ["{a.b}", "{a[0]}", "{a!r}", "{a:>5}", "{}", "{0}"],
)
def test_render_template_allows_only_plain_names(
    template: str,
) -> None:
    assert standard_tool_failure("render_template", {"template": template, "a": 1}) == (
        2,
        f"render_template allows only plain {{name}} placeholders; {template} is not one.",
    )


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param(
            {"template": "Dear {name},"},
            "render_template has no value for {name}.",
            id="missing-value",
        ),
        pytest.param(
            {"template": "oops }"},
            "render_template could not read the template: Single '}' encountered in format string.",
            id="single-brace",
        ),
        pytest.param(
            {"template": "{template}"},
            "render_template reserves the name 'template' for the template itself.",
            id="reserved-name",
        ),
        pytest.param(
            {"template": ["{a}"]},
            "render_template needs 'template' to be a string.",
            id="template-not-a-string",
        ),
        pytest.param({"a": 1}, "render_template needs the input 'template'.", id="no-template"),
    ],
)
def test_render_template_fails_explicitly(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("render_template", inputs) == (2, message)


# Shared contract


@pytest.mark.parametrize("name", ["chunk_text", "join_text", "render_template"])
def test_text_tools_grant_themselves_no_environment(
    name: str,
) -> None:
    for implementation in standard_document(name).implementations:
        assert implementation.environment == ()
        assert implementation.timeout_seconds == 60.0
