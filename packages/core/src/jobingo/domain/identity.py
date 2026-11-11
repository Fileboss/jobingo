"""The candidate's identity: stored apart from the CV, put back by code at render time.

`llm` can never import this module, which an import contract enforces.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

IdentityValue = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class Identity(BaseModel):
    # The client always receives and sends every field: one schema, all fields required.
    model_config = ConfigDict(
        json_schema_mode_override="serialization",
        json_schema_serialization_defaults_required=True,
    )

    name: IdentityValue = ""
    email: IdentityValue = ""
    phone: IdentityValue = ""
    address: IdentityValue = ""
    website: IdentityValue = ""
    linkedin: IdentityValue = ""
    github: IdentityValue = ""

    def contact_entries(self) -> list["ContactEntry"]:
        """The contact details as the CV prints them, in this order, the empty ones out."""
        entries: list[ContactEntry] = []
        if self.email:
            entries.append(ContactEntry(kind="email", text=self.email, href=f"mailto:{self.email}"))
        if self.phone:
            entries.append(ContactEntry(kind="phone", text=self.phone))
        if self.address:
            entries.append(ContactEntry(kind="address", text=self.address))
        if self.website:
            text = _without_scheme(self.website)
            entries.append(ContactEntry(kind="website", text=text, href=_https(text)))
        if self.linkedin:
            entries.append(_profile_entry("linkedin", self.linkedin, _LINKEDIN))
        if self.github:
            entries.append(_profile_entry("github", self.github, _GITHUB))
        return entries


type ContactKind = Literal["email", "phone", "address", "website", "linkedin", "github"]


class ContactEntry(BaseModel):
    kind: ContactKind
    # What is printed: a profile shows its username alone, beside its logo.
    text: str
    # Where it leads in the PDF, built by code: https or mailto only.
    href: str = ""


_SCHEME = re.compile(r"^(?:https?://)?(?:www\.)?", re.IGNORECASE)
# The username in a profile URL, or a bare username as typed.
_LINKEDIN = (
    re.compile(r"linkedin\.com/in/([^/?#\s]+)", re.IGNORECASE),
    "https://www.linkedin.com/in/",
)
_GITHUB = (re.compile(r"github\.com/([^/?#\s]+)", re.IGNORECASE), "https://github.com/")
_USERNAME = re.compile(r"^@?([\w.-]+)$")


_HOST_AND_PATH = re.compile(r"^[\w-]+(?:\.[\w-]+)+(?:/\S*)?$")


def _without_scheme(url: str) -> str:
    return _SCHEME.sub("", url.strip()).rstrip("/")


def _https(text: str) -> str:
    """A link only for what reads as an address: other text is printed, not linked."""
    return f"https://{text}" if _HOST_AND_PATH.match(text) else ""


def _profile_entry(
    kind: ContactKind, value: str, profile: tuple[re.Pattern[str], str]
) -> ContactEntry:
    """`linkedin.com/in/alex-moreau/` and `alex-moreau` both print `alex-moreau`. A value
    that is neither is printed as written, without its scheme."""
    pattern, base = profile
    found = pattern.search(value) or _USERNAME.match(value.strip())
    if found:
        username = found.group(1)
        return ContactEntry(kind=kind, text=username, href=base + username)
    text = _without_scheme(value)
    return ContactEntry(kind=kind, text=text, href=_https(text))
