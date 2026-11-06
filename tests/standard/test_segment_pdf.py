"""Tests for segment_pdf, the standard tool that divides a PDF into segments (ADR 0114)."""

import hashlib
import json
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
from pydantic import JsonValue

from azathoth.citations import (
    BoundingBox,
    CitationStatus,
    SegmentedText,
    SourcePage,
    verify_citation,
)
from azathoth.inputs import PDF_MEDIA_TYPE
from azathoth.tools import ToolDefinition
from tests.standard.harness import (
    run_standard_tool,
    standard_document,
    standard_implementation,
    standard_tool_failure,
)
from tests.standard.pdf_builder import Page, Text, pdf_document

PROJECT_ROOT = Path(__file__).parents[2]

STANDARD_README = PROJECT_ROOT / "src" / "azathoth" / "standard" / "README.md"

ADR = PROJECT_ROOT / "docs" / "adrs" / "0114-read-documents-with-tools.md"

INSTALL_GUIDE = PROJECT_ROOT / "docs" / "install.md"

MISSING_PDFMINER = (
    "segment_pdf needs pdfminer.six, which is not installed; install azathoth-ai[documents]."
)

ENCRYPTED = "segment_pdf cannot read the document: it is encrypted with a password."

DOCUMENTED = (
    "segment_pdf needs 'settings' to be an object.",
    "segment_pdf needs 'document' to be a content input.",
    "segment_pdf reads PDFs; 'document' is <MEDIA_TYPE>.",
    "segment_pdf needs 'max_pages' to be a whole number from 1 to 1000.",
    "segment_pdf does not take the input '<NAME>'.",
    MISSING_PDFMINER,
    ENCRYPTED,
    "segment_pdf found <PAGES> pages in the document, more than its max_pages of <MAX_PAGES>.",
    "segment_pdf could not read the document: <ERROR>: <REASON>.",
)
"""Every message the standard README documents for segment_pdf, placeholders included."""

LAYOUT = "line_overlap=0.5,char_margin=2.0,line_margin=0.5,word_margin=0.1,boxes_flow=0.5"

NAMED_PDF: dict[str, JsonValue] = {
    "path": "/tmp/document.pdf",
    "digest": "0" * 64,
    "media_type": PDF_MEDIA_TYPE,
}
"""A content input naming a PDF, for inputs refused before the file is read."""

CLAIM = Page(
    texts=(
        Text(72, 700, "Claim 0412."),
        Text(72, 686, "Filed by the insured."),
        Text(72, 500, "Received on December 14."),
    )
)
"""A page of two text boxes: two lines close together, and one line far below."""


def write_pdf(
    tmp_path: Path,
    pages: tuple[Page, ...],
    *,
    user_password: str | None = None,
) -> dict[str, JsonValue]:
    """Write a PDF of the pages given; return it as the engine gives a content input."""

    content = pdf_document(pages, user_password=user_password)
    path = tmp_path / "document.pdf"
    path.write_bytes(content)

    return {
        "path": str(path),
        "digest": hashlib.sha256(content).hexdigest(),
        "media_type": PDF_MEDIA_TYPE,
        "size_bytes": len(content),
    }


def segment(
    tmp_path: Path,
    *pages: Page,
) -> SegmentedText:
    """Run segment_pdf on a PDF of the pages given; return its extraction."""

    output = run_standard_tool("segment_pdf", {"document": write_pdf(tmp_path, pages)})

    assert set(output) == {"extraction"}

    return SegmentedText.model_validate(output["extraction"])


def boxes(
    segmented: SegmentedText,
) -> list[tuple[str, int | None, BoundingBox | None]]:
    """Return each segment's ID, page and box."""

    return [(segment.id, segment.page, segment.bbox) for segment in segmented.segments]


def test_each_text_box_is_one_segment_numbered_from_1_on_its_page(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, CLAIM, Page(texts=(Text(72, 700, "Page two."),)))

    assert segmented.text == (
        "Claim 0412.\nFiled by the insured.\n\nReceived on December 14.\n\nPage two."
    )
    assert [
        (segment.id, segment.page, segmented.segment_text(segment))
        for segment in segmented.segments
    ] == [
        ("p1.s1", 1, "Claim 0412.\nFiled by the insured."),
        ("p1.s2", 1, "Received on December 14."),
        ("p2.s1", 2, "Page two."),
    ]


def test_the_extraction_names_the_tool_its_library_and_its_layout(
    tmp_path: Path,
) -> None:
    document = write_pdf(tmp_path, (CLAIM,))
    output = run_standard_tool("segment_pdf", {"document": document})
    segmented = SegmentedText.model_validate(output["extraction"])

    assert segmented.tool == "segment_pdf"
    assert segmented.version == f"1.0.0 (pdfminer.six {version('pdfminer.six')}; {LAYOUT})"
    assert (segmented.source_digest, segmented.media_type) == (
        document["digest"],
        PDF_MEDIA_TYPE,
    )


def test_a_box_is_in_points_from_the_pages_top_left_corner(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, CLAIM)

    #
    # Helvetica descends 0.207 of its size below the baseline, so a 12-point
    # line set at 700 spans 697.516 to 709.516, 82.484 from the top of a
    # 792-point page. Widths are the font's own: 12/1000 of the sum of its
    # glyphs' widths, the longer line's for the first box.
    #
    assert boxes(segmented) == [
        ("p1.s1", 1, BoundingBox(left=72.0, top=82.48, width=108.05, height=26.0)),
        ("p1.s2", 1, BoundingBox(left=72.0, top=282.48, width=145.39, height=12.0)),
    ]


def test_a_box_is_measured_from_the_crop_box(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(72, 700, "Cropped."),), crop_box=(50, 100, 562, 742)),
    )

    assert boxes(segmented) == [
        ("p1.s1", 1, BoundingBox(left=22.0, top=32.48, width=49.36, height=12.0)),
    ]


def test_a_box_is_measured_from_a_media_box_that_does_not_start_at_zero(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(172, 900, "Offset."),), media_box=(100, 200, 712, 992)),
    )

    assert boxes(segmented) == [
        ("p1.s1", 1, BoundingBox(left=72.0, top=82.48, width=35.35, height=12.0)),
    ]


def test_a_box_is_clipped_to_the_crop_box(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(40, 700, "Clipped."),), crop_box=(50, 0, 612, 705)),
    )

    (found,) = segmented.segments

    assert found.bbox == BoundingBox(left=0.0, top=0.0, width=34.02, height=7.48)


def test_a_segment_outside_the_crop_box_names_its_page_and_no_box(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(
            texts=(Text(72, 700, "Shown."), Text(72, 100, "Cropped away.")),
            crop_box=(0, 400, 612, 792),
        ),
    )

    assert [(segment.id, segment.bbox is None) for segment in segmented.segments] == [
        ("p1.s1", False),
        ("p1.s2", True),
    ]


@pytest.mark.parametrize("rotate", [90, 180, 270])
def test_a_segment_on_a_rotated_page_names_its_page_and_no_box(
    tmp_path: Path,
    rotate: int,
) -> None:
    segmented = segment(tmp_path, Page(texts=(Text(72, 700, "Turned."),), rotate=rotate))

    assert [(segment.id, segment.page, segment.bbox) for segment in segmented.segments] == [
        ("p1.s1", 1, None),
    ]


def test_a_page_with_no_text_has_no_segments_and_numbers_the_next_page_on(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, Page(), Page(texts=(Text(72, 700, "After."),)))

    assert segmented.text == "After."
    assert [(segment.id, segment.page) for segment in segmented.segments] == [("p2.s1", 2)]


def test_a_pdf_with_no_text_is_an_empty_extraction(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, Page(), Page())

    assert (segmented.text, segmented.segments) == ("", ())


def test_ligatures_are_written_out_as_their_letters(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, Page(texts=(Text(72, 700, "The \ufb01le was \ufb02agged."),)))

    assert segmented.text == "The file was flagged."


def test_a_hyphen_that_ends_a_line_is_kept(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(72, 700, "The adjuster re-"), Text(72, 686, "viewed it."))),
    )

    assert segmented.text == "The adjuster re-\nviewed it."


def test_text_is_put_in_nfc(
    tmp_path: Path,
) -> None:
    #
    # WinAnsi has e with an acute accent as one code, so the text is
    # composed already; NFC must leave it so.
    #
    segmented = segment(tmp_path, Page(texts=(Text(72, 700, "R\u00e9sum\u00e9."),)))

    assert segmented.text == "R\u00e9sum\u00e9."


def test_a_segment_cites_and_anchors_on_its_page_and_box(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, CLAIM)
    check = verify_citation(segmented, segment_id="p1.s2", quote="December 14")

    assert check.status is CitationStatus.VERIFIED
    assert check.anchor is not None
    assert [selector.model_dump(by_alias=True) for selector in check.anchor.selectors][2] == {
        "type": "FragmentSelector",
        "value": "page=1&viewrect=72,282.48,145.39,12",
        "conformsTo": "http://tools.ietf.org/rfc/rfc3778",
    }


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param(
            {"document": "/tmp/document.pdf"},
            "segment_pdf needs 'document' to be a content input.",
            id="not-an-object",
        ),
        pytest.param(
            {"document": {"path": "/tmp/document.pdf", "media_type": PDF_MEDIA_TYPE}},
            "segment_pdf needs 'document' to be a content input.",
            id="no-digest",
        ),
        pytest.param(
            {},
            "segment_pdf needs 'document' to be a content input.",
            id="missing",
        ),
        pytest.param(
            {
                "document": {
                    "path": "/tmp/document.png",
                    "digest": "0" * 64,
                    "media_type": "image/png",
                }
            },
            "segment_pdf reads PDFs; 'document' is image/png.",
            id="image",
        ),
        pytest.param(
            {"document": {}, "pages": 3},
            "segment_pdf does not take the input 'pages'.",
            id="unknown-input",
        ),
        pytest.param(
            {"document": NAMED_PDF, "settings": [1]},
            "segment_pdf needs 'settings' to be an object.",
            id="settings-not-an-object",
        ),
        pytest.param(
            {"document": "/tmp/document.pdf", "settings": 3},
            "segment_pdf needs 'settings' to be an object.",
            id="settings-before-document",
        ),
        pytest.param(
            {"document": NAMED_PDF, "settings": {"max_pages": 0}},
            "segment_pdf needs 'max_pages' to be a whole number from 1 to 1000.",
            id="max-pages-zero",
        ),
        pytest.param(
            {"document": NAMED_PDF, "settings": {"max_pages": 1001}},
            "segment_pdf needs 'max_pages' to be a whole number from 1 to 1000.",
            id="max-pages-too-many",
        ),
        pytest.param(
            {"document": NAMED_PDF, "settings": {"max_pages": 2.5}},
            "segment_pdf needs 'max_pages' to be a whole number from 1 to 1000.",
            id="max-pages-fraction",
        ),
        pytest.param(
            {"document": NAMED_PDF, "settings": {"max_pages": True}},
            "segment_pdf needs 'max_pages' to be a whole number from 1 to 1000.",
            id="max-pages-boolean",
        ),
    ],
)
def test_inputs_it_cannot_use_exit_with_status_2(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("segment_pdf", inputs) == (2, message)


def test_a_file_that_is_not_a_pdf_exits_with_status_1(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.pdf"
    path.write_bytes(b"%PDF-1.7\nnot really\n")

    status, message = standard_tool_failure(
        "segment_pdf",
        {
            "document": {
                "path": str(path),
                "digest": "0" * 64,
                "media_type": PDF_MEDIA_TYPE,
            }
        },
    )

    assert status == 1
    assert message.startswith("segment_pdf could not read the document: ")
    assert message.endswith(".")


def standard_implementation_definition() -> ToolDefinition:
    """Return segment_pdf's definition."""

    return standard_document("segment_pdf").definition


def run_without_site_packages(
    tmp_path: Path,
    inputs: dict[str, JsonValue],
) -> subprocess.CompletedProcess[str]:
    """Run segment_pdf's source with a Python that cannot import pdfminer."""

    script = tmp_path / "segment_pdf.py"
    script.write_text(standard_implementation("segment_pdf").source, encoding="utf-8")

    return subprocess.run(
        [sys.executable, "-S", "-I", str(script)],
        input=json.dumps(inputs),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_without_pdfminer_it_says_which_extra_to_install(
    tmp_path: Path,
) -> None:
    completed = run_without_site_packages(tmp_path, {"document": write_pdf(tmp_path, (CLAIM,))})

    assert completed.returncode == 1
    assert completed.stderr == MISSING_PDFMINER
    assert completed.stdout == ""


def test_without_pdfminer_bad_inputs_are_still_refused_first(
    tmp_path: Path,
) -> None:
    completed = run_without_site_packages(tmp_path, {"document": {}})

    assert completed.returncode == 2
    assert completed.stderr == "segment_pdf needs 'document' to be a content input."


def script() -> dict[str, Any]:
    """Load segment_pdf's source as a module that does not run, and return its names."""

    namespace: dict[str, Any] = {"__name__": "segment_pdf"}

    exec(compile(standard_implementation("segment_pdf").source, "segment_pdf", "exec"), namespace)

    return namespace


def test_it_writes_out_exactly_the_latin_ligatures() -> None:
    assert script()["LIGATURES"] == {
        chr(code): letters
        for code, letters in zip(
            range(0xFB00, 0xFB07),
            ("ff", "fi", "fl", "ffi", "ffl", "st", "st"),
            strict=True,
        )
    }


def test_the_implementation_takes_its_document_as_content_and_keeps_its_extraction() -> None:
    implementation = standard_implementation("segment_pdf")

    assert implementation.content_inputs == ("document",)
    assert implementation.extraction_output == "extraction"
    assert implementation.environment == ()
    assert implementation.timeout_seconds == 300.0


def test_the_readme_documents_exactly_the_tools_messages() -> None:
    text = STANDARD_README.read_text(encoding="utf-8")
    section = text[text.index("### segment_pdf") : text.index("## Installing")]
    documented = {
        line
        for block in section.split("```text\n")[1:]
        for line in block.split("```", 1)[0].splitlines()
    }

    assert documented == set(DOCUMENTED)


def test_the_documented_extraction_version_is_the_layout_the_tool_uses() -> None:
    expected = f"1.0.0 (pdfminer.six 20260107; {LAYOUT})"
    tool = script()

    assert tool["extraction_version"]("20260107") == expected
    assert f"\n{expected}\n" in ADR.read_text(encoding="utf-8")
    assert f'"version": "{expected}"' in STANDARD_README.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "path",
    [pytest.param(path, id=path.name) for path in (STANDARD_README, ADR, INSTALL_GUIDE)],
)
def test_the_documented_missing_extra_message_is_the_real_one(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")

    assert f"{MISSING_PDFMINER}\n" in text
    assert 'python -m pip install "azathoth-ai[documents]"' in text


def test_the_documents_extra_installs_pdfminer_and_development_does_too() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    assert extras["documents"] == ["pdfminer.six>=20260107"]
    assert "pdfminer.six>=20260107" in extras["dev"]
    assert not any("pdfminer" in requirement for requirement in project["project"]["dependencies"])


def test_the_schemas_take_a_document_and_give_an_extraction() -> None:
    definition = standard_implementation_definition()

    assert definition.input_schema.json_schema == {
        "type": "object",
        "properties": {
            "settings": {
                "type": "object",
                "properties": {"max_pages": {"type": "integer", "minimum": 1, "maximum": 1000}},
            },
            "document": {"type": "object"},
        },
        "required": ["document"],
    }
    assert definition.output_schema.json_schema == {
        "type": "object",
        "properties": {"extraction": {"type": "object"}},
        "required": ["extraction"],
    }


def test_each_line_is_trimmed_of_the_whitespace_around_it(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(72, 700, "Spaced.   "), Text(72, 686, "   Indented."))),
    )

    assert segmented.text == "Spaced.\nIndented."


def test_a_line_of_only_whitespace_is_left_out(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(72, 700, "Above."), Text(72, 686, "     "), Text(72, 672, "Below."))),
    )

    assert [segmented.segment_text(segment) for segment in segmented.segments] == [
        "Above.",
        "Below.",
    ]


def test_a_box_of_only_whitespace_is_no_segment(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(72, 700, "Alone."), Text(72, 400, "     "))),
    )

    assert [(segment.id, segmented.segment_text(segment)) for segment in segmented.segments] == [
        ("p1.s1", "Alone."),
    ]


def test_a_combining_accent_is_composed(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, Page(texts=(Text(72, 700, "Cafe\u0301."),)))

    assert segmented.text == "Caf\u00e9."


def test_a_page_drawing_is_no_segment(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(72, 700, "Ruled."),), rectangles=((72, 600, 200, 50),)),
    )

    assert [segment.id for segment in segmented.segments] == ["p1.s1"]


def test_a_box_past_the_crop_boxs_right_edge_is_clipped_to_it(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        Page(texts=(Text(500, 700, "Past the right edge."),), crop_box=(0, 0, 550, 792)),
    )

    assert boxes(segmented) == [
        ("p1.s1", 1, BoundingBox(left=500.0, top=82.48, width=50.0, height=12.0)),
    ]


def test_every_page_is_listed_with_its_size_and_whether_it_has_text(
    tmp_path: Path,
) -> None:
    segmented = segment(
        tmp_path,
        CLAIM,
        Page(),
        Page(texts=(Text(72, 700, "Cropped."),), crop_box=(50, 100, 562, 742)),
    )

    assert segmented.pages == (
        SourcePage(page=1, width=612.0, height=792.0, has_text=True),
        SourcePage(page=2, width=612.0, height=792.0, has_text=False),
        SourcePage(page=3, width=512.0, height=642.0, has_text=True),
    )


@pytest.mark.parametrize(
    ("rotate", "size"),
    [(90, (700.0, 600.0)), (180, (600.0, 700.0)), (270, (700.0, 600.0))],
)
def test_a_rotated_page_is_listed_at_its_size_as_it_is_shown(
    tmp_path: Path,
    rotate: int,
    size: tuple[float, float],
) -> None:
    segmented = segment(tmp_path, Page(crop_box=(0, 0, 600, 700), rotate=rotate))

    (page,) = segmented.pages

    assert (page.width, page.height) == size


def test_a_page_of_only_whitespace_is_listed_with_no_text(
    tmp_path: Path,
) -> None:
    segmented = segment(tmp_path, Page(texts=(Text(72, 700, "     "),)))

    assert segmented.pages == (SourcePage(page=1, width=612.0, height=792.0, has_text=False),)


def test_a_pdf_of_more_pages_than_max_pages_is_refused(
    tmp_path: Path,
) -> None:
    document = write_pdf(tmp_path, (CLAIM, CLAIM, CLAIM))

    assert standard_tool_failure(
        "segment_pdf", {"document": document, "settings": {"max_pages": 2}}
    ) == (1, "segment_pdf found 3 pages in the document, more than its max_pages of 2.")


def test_a_pdf_of_exactly_max_pages_is_read(
    tmp_path: Path,
) -> None:
    document = write_pdf(tmp_path, (CLAIM, CLAIM))
    output = run_standard_tool("segment_pdf", {"document": document, "settings": {"max_pages": 2}})

    assert len(SegmentedText.model_validate(output["extraction"]).pages) == 2


def test_settings_may_be_left_out_or_empty(
    tmp_path: Path,
) -> None:
    document = write_pdf(tmp_path, (CLAIM,))

    assert run_standard_tool("segment_pdf", {"document": document}) == run_standard_tool(
        "segment_pdf", {"document": document, "settings": {}}
    )


def test_max_pages_defaults_to_300_and_goes_up_to_1000() -> None:
    tool = script()

    assert (tool["DEFAULT_MAX_PAGES"], tool["MAX_PAGES"]) == (300, 1000)


def test_by_default_a_pdf_of_301_pages_is_refused(
    tmp_path: Path,
) -> None:
    document = write_pdf(tmp_path, (Page(),) * 301)

    assert standard_tool_failure("segment_pdf", {"document": document}) == (
        1,
        "segment_pdf found 301 pages in the document, more than its max_pages of 300.",
    )


def test_a_pdf_that_needs_a_password_is_refused(
    tmp_path: Path,
) -> None:
    document = write_pdf(tmp_path, (CLAIM,), user_password="secret")

    assert standard_tool_failure("segment_pdf", {"document": document}) == (1, ENCRYPTED)


def test_a_pdf_encrypted_with_an_empty_user_password_is_read(
    tmp_path: Path,
) -> None:
    open_pdf = segment(tmp_path, CLAIM)
    document = write_pdf(tmp_path, (CLAIM,), user_password="")
    output = run_standard_tool("segment_pdf", {"document": document})
    encrypted = SegmentedText.model_validate(output["extraction"])

    assert (encrypted.text, encrypted.segments, encrypted.pages) == (
        open_pdf.text,
        open_pdf.segments,
        open_pdf.pages,
    )
