"""Tests that the user-facing documentation stays navigable and cross-platform."""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]

TOP_LEVEL_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "RELEASING.md",
)

USER_GUIDES = (
    "docs/install.md",
    "docs/openrouter.md",
)

FENCE = re.compile(r"^\s*```(?P<language>\S*)\s*$")

HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")

PLATFORM_ONLY_LANGUAGES = {
    "macOS": "bash",
    "Windows": "powershell",
}

INLINE_CODE = re.compile(r"`[^`]*`")

LINK = re.compile(r"\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")

EXTERNAL_SCHEMES = (
    "http://",
    "https://",
    "mailto:",
)


def linked_documents() -> tuple[str, ...]:
    """Return every documentation file whose relative links must resolve."""

    documents = [
        document for document in TOP_LEVEL_DOCUMENTS if (PROJECT_ROOT / document).is_file()
    ]
    documents.extend(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted((PROJECT_ROOT / "docs").glob("*.md"))
    )
    documents.extend(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted((PROJECT_ROOT / "examples").rglob("*.md"))
    )

    return tuple(documents)


def fenced_blocks(
    text: str,
) -> tuple[tuple[int, str, str], ...]:
    """Return the opening line, language and governing heading of each fenced block."""

    blocks: list[tuple[int, str, str]] = []
    inside = False
    heading = ""

    for number, line in enumerate(text.splitlines(), start=1):
        match = FENCE.match(line)

        if match is None:
            heading_match = None if inside else HEADING.match(line)

            if heading_match is not None:
                heading = heading_match.group("title")

            continue

        if inside:
            inside = False
        else:
            inside = True
            blocks.append((number, match.group("language"), heading))

    return tuple(blocks)


def is_platform_only(
    language: str,
    heading: str,
) -> bool:
    """Report whether a block sits under a heading for the one platform it targets."""

    words = set(re.findall(r"[A-Za-z]+", heading))

    return any(
        platform in words and platform_language == language
        for platform, platform_language in PLATFORM_ONLY_LANGUAGES.items()
    )


def unpaired_shell_blocks(
    text: str,
) -> tuple[int, ...]:
    """Return the lines of shell blocks that lack their other-platform equivalent."""

    blocks = fenced_blocks(text)
    unpaired: list[int] = []

    for index, (number, language, heading) in enumerate(blocks):
        if is_platform_only(language, heading):
            continue

        if language == "bash":
            following = blocks[index + 1][1] if index + 1 < len(blocks) else ""

            if following != "powershell":
                unpaired.append(number)

        if language == "powershell":
            preceding = blocks[index - 1][1] if index > 0 else ""

            if preceding != "bash":
                unpaired.append(number)

    return tuple(unpaired)


def prose_lines(
    text: str,
) -> tuple[tuple[int, str], ...]:
    """Return the numbered lines outside fenced blocks, without inline code."""

    lines: list[tuple[int, str]] = []
    inside = False

    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line) is not None:
            inside = not inside
            continue

        if not inside:
            lines.append((number, INLINE_CODE.sub("", line)))

    return tuple(lines)


def relative_link_targets(
    text: str,
) -> tuple[tuple[int, str], ...]:
    """Return the numbered relative link targets in a Markdown document."""

    targets: list[tuple[int, str]] = []

    for number, line in prose_lines(text):
        for match in LINK.finditer(line):
            target = match.group("target")

            if target.startswith(EXTERNAL_SCHEMES) or target.startswith("#"):
                continue

            targets.append((number, target.split("#", 1)[0]))

    return tuple(targets)


def test_fenced_blocks_report_opening_lines_languages_and_headings() -> None:
    text = (
        "## Setup\n```bash\n# not a heading\nls\n```\n\n"
        "### Windows\n```powershell\nGet-ChildItem\n```\n"
    )

    assert fenced_blocks(text) == (
        (2, "bash", "Setup"),
        (8, "powershell", "Windows"),
    )


def test_paired_shell_blocks_are_accepted() -> None:
    text = "## Run\n```bash\nls\n```\n```powershell\nGet-ChildItem\n```\n"

    assert unpaired_shell_blocks(text) == ()


def test_lone_shell_blocks_are_reported() -> None:
    text = "## Run\n```bash\nls\n```\n```text\nout\n```\n```powershell\ndir\n```\n"

    assert unpaired_shell_blocks(text) == (2, 8)


def test_platform_sections_may_hold_their_own_shell_only() -> None:
    text = (
        "### macOS\n```bash\nbrew install python\n```\n"
        "### Windows: scripts\n```powershell\nSet-ExecutionPolicy\n```\n"
        "### macOS\n```powershell\nwinget\n```\n"
    )

    assert unpaired_shell_blocks(text) == (10,)


def test_relative_link_targets_skip_code_external_links_and_anchors() -> None:
    text = (
        "See [install](docs/install.md#python) and [site](https://example.com).\n"
        "Jump [here](#top). Not `[code](missing.md)`.\n"
        "```text\n[fenced](missing.md)\n```\n"
    )

    assert relative_link_targets(text) == ((1, "docs/install.md"),)


@pytest.mark.parametrize("document", linked_documents())
def test_relative_links_resolve(
    document: str,
) -> None:
    path = PROJECT_ROOT / document
    broken = [
        f"{document}:{number}: {target}"
        for number, target in relative_link_targets(path.read_text(encoding="utf-8"))
        if not (path.parent / target).exists()
    ]

    assert broken == []


@pytest.mark.parametrize("guide", USER_GUIDES)
def test_every_shell_command_has_both_platforms(
    guide: str,
) -> None:
    text = (PROJECT_ROOT / guide).read_text(encoding="utf-8")
    unpaired = [f"{guide}:{number}" for number in unpaired_shell_blocks(text)]

    assert unpaired == []
