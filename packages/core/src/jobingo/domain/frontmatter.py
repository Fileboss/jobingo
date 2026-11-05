from typing import Any, cast

import yaml


def split_front_matter(text: str) -> tuple[dict[str, Any], str, int]:
    """Split a leading ``---`` YAML block from Markdown body.

    Returns (metadata, body, body_start_line) where body_start_line is the
    1-indexed line number of the first body line, so downstream parsers can
    report accurate line numbers for the remainder of the file.

    Raises ValueError on a block that is not a closed YAML mapping.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, 1

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw = "\n".join(lines[1:i])
            try:
                metadata: object = yaml.safe_load(raw) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"front-matter invalide : {exc}") from exc
            if not isinstance(metadata, dict):
                raise ValueError("front-matter invalide : un mapping YAML est attendu")
            body = "\n".join(lines[i + 1 :])
            return cast(dict[str, Any], metadata), body, i + 2

    raise ValueError("front-matter invalide : marqueur de fermeture '---' manquant")


def lenient_front_matter(text: str) -> tuple[dict[str, Any], str, int]:
    """`split_front_matter`, reading a broken block as ordinary text: a broken
    block is a diagnostic for the user, never a reason to refuse their CV."""
    try:
        return split_front_matter(text)
    except ValueError:
        return {}, text, 1
