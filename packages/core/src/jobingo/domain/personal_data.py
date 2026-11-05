import re
import unicodedata

from pydantic import BaseModel

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+33[\s.-]?|0)[1-9](?:[\s.-]?\d{2}){4}")
# A profile is often written without its scheme: `linkedin.com/in/alex`.
_URL_RE = re.compile(r"(?:https?://|www\.|(?:linkedin|github|gitlab)\.com/)\S+", re.IGNORECASE)

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", _EMAIL_RE),
    ("phone", _PHONE_RE),
    ("url", _URL_RE),
]


class PersonalDataFinding(BaseModel):
    line_no: int
    kind: str  # email | phone | url
    snippet: str


CANDIDATE_PLACEHOLDER = "[CANDIDAT]"


def _accent_variants() -> dict[str, str]:
    """Base letter → every Latin letter that folds to it (`e` → `eéèêë…`)."""
    variants: dict[str, set[str]] = {}
    for code in range(0x00C0, 0x0180):
        char = chr(code)
        base = "".join(
            c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)
        ).lower()
        if len(base) == 1 and base.isalpha() and base.isascii():
            variants.setdefault(base, {base}).update({char.lower(), char.upper()})
    return {base: "".join(sorted(chars)) for base, chars in variants.items()}


_ACCENTS = _accent_variants()
_PHONE_VALUE_RE = re.compile(r"^\+?[\d\s.()-]{8,}$")
_PHONE_SEP = r"[\s.-]?"


def _fold_char(char: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)
    ).lower()


def _value_pattern(value: str) -> str:
    """A regex for one identity value, as it may appear in someone else's text.

    A phone number matches whatever its spacing and with `+33` for the leading
    0; a name matches with or without its accents (« Hélène », « Helene »).
    """
    digits = re.sub(r"\D", "", value)
    if _PHONE_VALUE_RE.match(value) and len(digits) >= 8:
        if value.lstrip().startswith("+33") or digits.startswith("0033"):
            digits = "0" + digits.removeprefix("00").removeprefix("33")
        if digits.startswith("0") and len(digits) >= 9:
            head = rf"(?:\+33{_PHONE_SEP}(?:\(0\){_PHONE_SEP})?|0033{_PHONE_SEP}|0)"
            return head + _PHONE_SEP.join(re.escape(d) for d in digits[1:])
        return _PHONE_SEP.join(re.escape(d) for d in digits)
    parts: list[str] = []
    for char in value:
        base = _fold_char(char)
        if char.isspace():
            parts.append(r"\s+")  # a name wrapped over two lines, or double-spaced
        elif len(base) == 1 and base in _ACCENTS:
            parts.append(f"[{_ACCENTS[base]}]")
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def redact(text: str, values: list[str]) -> str:
    """Replace the candidate's own name, e-mail and phone with `[CANDIDAT]`
    before the text reaches the model.

    External content is the reachable path: a forwarded job alert or a
    recruiter's e-mail names the user. Values are matched case-insensitively
    and longest-first, so a full name is replaced before its parts.

    Only whole words are replaced — not « Morel » inside « Morelli », nor « Martin »
    inside « Saint-Martin » — since the redacted text may also get stored.
    """
    for value in sorted({v.strip() for v in values if v and v.strip()}, key=len, reverse=True):
        # A hyphen glued to the value means a compound (« Saint-Martin »).
        pattern = rf"(?<![\w-]){_value_pattern(value)}(?![\w-])"
        text = re.sub(pattern, CANDIDATE_PLACEHOLDER, text, flags=re.IGNORECASE)
    return text


def find_personal_data(text: str) -> list[PersonalDataFinding]:
    """Flag e-mail addresses, phone numbers and profile URLs.

    The CV must carry no personal data: identity is stored apart and put back at
    render time. This is advisory, it flags the line and does not block a save.
    """
    findings: list[PersonalDataFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(
                    PersonalDataFinding(line_no=line_no, kind=kind, snippet=match.group(0))
                )
    return findings
