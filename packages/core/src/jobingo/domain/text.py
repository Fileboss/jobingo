import unicodedata


def fold(text: str) -> str:
    """Casefold and strip accents, so that `Résumé` matches `resume`."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))
