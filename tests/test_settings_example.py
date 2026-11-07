"""The example settings file is what the user copies: it must name real settings."""

import re
from pathlib import Path

from jobingo.config import Settings

EXAMPLE = Path(__file__).parent.parent / ".env.example"
_LINE = re.compile(r"^#?\s*([A-Z][A-Z0-9_]+)=(.*)$")


def _entries() -> list[tuple[str, str, bool]]:
    entries: list[tuple[str, str, bool]] = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line.strip())
        if match:
            entries.append((match.group(1), match.group(2), line.startswith("#")))
    return entries


def test_every_example_setting_exists():
    """A misspelt name would be ignored silently, and Gmail would never be used."""
    known = {name.upper() for name in Settings.model_fields}
    unknown = [name for name, _, _ in _entries() if name not in known]
    assert unknown == []


def test_the_uncommented_values_are_the_defaults():
    """Read from the fields' declared defaults: building `Settings` would read the
    developer's own settings file, which tests never read."""
    for name, value, commented in _entries():
        if commented:
            continue
        default = Settings.model_fields[name.lower()].default
        shown = default.get_secret_value() if hasattr(default, "get_secret_value") else default
        assert str(shown).lower() == value.lower(), name


def test_the_gmail_block_sets_both_servers():
    commented = {name for name, _, is_comment in _entries() if is_comment}
    assert {"MAIL_IMAP_HOST", "MAIL_IMAP_PASSWORD", "MAIL_SMTP_HOST", "MAIL_SMTP_PASSWORD"} <= (
        commented
    )
