"""A cover letter: the template owns the frame (date, recipient, subject, closing,
signature), the model writes only the slots, and code checks each slot.

The CV's rule carries over with one difference. A refused CV rewrite falls back to the
user's own line; a letter slot has no original, so a refused slot comes back empty,
with the model's text beside it and the reason. The user then writes it, or adopts it
knowingly: the checks frame the model, not the person signing the letter.
"""

from typing import Any, Literal, cast

from pydantic import BaseModel, model_validator

from jobingo.domain.style import StyleGuide, forbidden_hits
from jobingo.domain.text_checks import count_words, numbers_in, unsourced_proper_nouns

type SourceName = Literal["realisations", "offre", "notes_entreprise"]
ALL_SOURCES: tuple[SourceName, ...] = ("realisations", "offre", "notes_entreprise")


class SlotSpec(BaseModel):
    name: str
    max_words: int
    # Where the slot's figures and proper nouns may come from. None declared: all.
    sources: list[SourceName] = []

    def allowed(self) -> tuple[SourceName, ...]:
        return tuple(self.sources) or ALL_SOURCES


class LetterManifest(BaseModel):
    """The letter template's `manifest.yaml`. It ships with the code, so a bad one is
    a bug and fails on load; a test checks that its slots match its body."""

    name: str
    langs: list[str]
    max_pages: int
    slots: list[SlotSpec]

    def slot(self, name: str) -> SlotSpec | None:
        return next((slot for slot in self.slots if slot.name == name), None)


class SlotText(BaseModel):
    name: str
    text: str


class LetterProposalSchema(BaseModel):
    """What the API is asked to answer. Strict structured output forbids a free-form
    mapping, so the slots travel as named pairs."""

    slots: list[SlotText] = []
    cited_ids: list[str] = []


class LetterProposal(BaseModel):
    slots: dict[str, str] = {}
    cited_ids: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _pairs(cls, data: Any) -> Any:
        """Fold the `[{name, text}]` pairs of `LetterProposalSchema` back into a mapping."""
        if not isinstance(data, dict):
            return data
        raw = cast(dict[str, Any], data)
        pairs: object = raw.get("slots")
        if not isinstance(pairs, list):
            return raw
        folded: dict[str, str] = {}
        for pair in cast(list[object], pairs):
            if isinstance(pair, dict):
                entry = cast(dict[str, Any], pair)
                if "name" in entry:
                    folded[str(entry["name"])] = str(entry.get("text", ""))
        return {**raw, "slots": folded}


class LetterSources(BaseModel):
    """The texts a slot's facts may come from, as the user can read them."""

    realisations: str = ""
    offre: str = ""
    notes_entreprise: str = ""

    def text_for(self, spec: SlotSpec) -> str:
        return "\n".join(getattr(self, source) for source in spec.allowed())


def validate_slot(
    text: str, spec: SlotSpec, sources: LetterSources, style: StyleGuide
) -> str | None:
    """Why a slot the model wrote must be refused, in French, or None."""
    text = text.strip()
    if not text:
        return None
    words = count_words(text)
    if words > spec.max_words:
        return f"{words} mots, le modèle en autorise {spec.max_words}"
    known = numbers_in(sources.text_for(spec))
    invented = [number for number in numbers_in(text) if number not in known]
    if invented:
        return f"chiffre absent des sources : {invented[0]}"
    hits = forbidden_hits(text, style.forbidden)
    if hits:
        return f"tournure interdite : {hits[0]}"
    return None


class SlotDraft(BaseModel):
    """One slot as the model's answer left it, after the checks."""

    name: str
    max_words: int
    text: str  # empty when the proposal was refused
    proposed: str
    rejected_reason: str
    # Proper nouns of an accepted proposal its sources never mention: to check.
    unsourced_names: list[str]


class LetterDraft(BaseModel):
    slots: list[SlotDraft]
    cited_ids: list[str]
    # Slots not written, unknown slots or ids in the answer: dropped, and said.
    warnings: list[str]


def build_letter_draft(
    proposal: LetterProposal,
    manifest: LetterManifest,
    sources: LetterSources,
    style: StyleGuide,
    *,
    known_ids: set[str],
) -> LetterDraft:
    warnings: list[str] = []
    slots: list[SlotDraft] = []
    for spec in manifest.slots:
        proposed = (proposal.slots.get(spec.name) or "").strip()
        if not proposed:
            warnings.append(f"l'emplacement « {spec.name} » n'a pas été rédigé")
        reason = validate_slot(proposed, spec, sources, style)
        slots.append(
            SlotDraft(
                name=spec.name,
                max_words=spec.max_words,
                text="" if reason else proposed,
                proposed=proposed,
                rejected_reason=reason or "",
                unsourced_names=(
                    []
                    if reason or not proposed
                    else unsourced_proper_nouns(proposed, sources.text_for(spec))
                ),
            )
        )
    declared = {spec.name for spec in manifest.slots}
    warnings += [
        f"emplacement inconnu proposé, ignoré : « {name} »"
        for name in proposal.slots
        if name not in declared
    ]
    cited: list[str] = []
    for item_id in proposal.cited_ids:
        if item_id not in known_ids:
            warnings.append(f"réalisation citée inconnue, ignorée : « {item_id} »")
        elif item_id not in cited:
            cited.append(item_id)
    return LetterDraft(slots=slots, cited_ids=cited, warnings=warnings)


def letter_problems(texts: dict[str, str], manifest: LetterManifest) -> list[str]:
    """What keeps the letter from being downloaded: an empty slot, or one over its
    limit. The user's own words are not checked for facts: they are theirs."""
    problems: list[str] = []
    for spec in manifest.slots:
        text = texts.get(spec.name, "").strip()
        if not text:
            problems.append(f"« {spec.name} » est vide")
        elif (words := count_words(text)) > spec.max_words:
            problems.append(f"« {spec.name} » fait {words} mots, {spec.max_words} au plus")
    return problems
