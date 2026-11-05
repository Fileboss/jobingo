"""The registers only help if every entry is well formed and reachable from its index,
which is the part that gets loaded in every session."""

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs"
REGISTERS = {
    "decisions": ["## Question", "## Decision", "## Why"],
    "lessons": ["## What happened", "## What to do instead", "## Prevention"],
}
INDEX_LINE = re.compile(r"^- \[[^\]]+\]\(([^)]+\.md)\): when .+$")
FILE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")


def _entries(register: str) -> list[Path]:
    return [path for path in (DOCS / register).glob("*.md") if path.name != "INDEX.md"]


def _front_matter(path: Path) -> dict[str, str]:
    _, block, _ = path.read_text(encoding="utf-8").split("---\n", 2)
    return dict(line.split(": ", 1) for line in block.splitlines())


def _indexed(register: str) -> list[str]:
    lines = (DOCS / register / "INDEX.md").read_text(encoding="utf-8").splitlines()
    entries = [line for line in lines if line.startswith("- ")]
    for line in entries:
        assert INDEX_LINE.match(line), f"malformed index line: {line}"
    return [match.group(1) for line in entries if (match := INDEX_LINE.match(line))]


def test_claude_md_stays_short():
    """It loads in every session. Details belong in `docs/` or `.claude/rules/`."""
    lines = (DOCS.parent / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 200


@pytest.mark.parametrize("register", REGISTERS)
def test_entries_are_well_formed(register: str):
    for path in _entries(register):
        assert FILE_NAME.match(path.name), path.name
        front_matter = _front_matter(path)
        assert front_matter["status"] in ("active", "superseded"), path.name
        assert front_matter["applies_when"], path.name
        text = path.read_text(encoding="utf-8")
        for heading in REGISTERS[register]:
            assert f"\n{heading}\n" in text, f"{path.name} has no {heading}"


@pytest.mark.parametrize("register", REGISTERS)
def test_the_index_lists_exactly_the_active_entries(register: str):
    active = {path.name for path in _entries(register) if _front_matter(path)["status"] == "active"}
    indexed = _indexed(register)

    assert len(indexed) == len(set(indexed))
    assert set(indexed) == active
