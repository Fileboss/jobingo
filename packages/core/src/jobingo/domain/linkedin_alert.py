"""LinkedIn job alerts, read in code. An alert card carries only a title, a company, a
location and a link, and that structure is regular enough to need no model."""

import re

from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel

from jobingo.domain.mail import bare_address


class AlertOffer(BaseModel):
    job_id: str
    title: str
    company_name: str
    location: str = ""
    url: str


_JOB_URL_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?\s]*-)?(\d{5,})")

# Buttons and badges next to a card's text, which are neither the company nor the
# location. Matched case-insensitively against a whole line.
_NOISE_RE = re.compile(
    r"^(postuler|apply|voir l['’]offre|view job|candidature simplifi[ée]e|easy apply|"
    r"soyez parmi les premiers.*|be an early applicant|actively recruiting|"
    r"recrutement actif|promu|promoted|nouveau|new|\d+\s*(candidats?|applicants?).*|"
    r"il y a .*|\d+\s*(hours?|days?|weeks?) ago)$",
    re.IGNORECASE,
)
_SEPARATORS = (" · ", " • ", " | ")


def is_linkedin_sender(from_addr: str) -> bool:
    """The address itself, not the display name: `linkedin.com <x@evil.test>` is not."""
    return bare_address(from_addr).endswith("@linkedin.com")


def _split_company_location(lines: list[str]) -> tuple[str, str]:
    for line in lines:
        for separator in _SEPARATORS:
            if separator in line:
                company, _, location = line.partition(separator)
                return company.strip(), location.strip()
    company = lines[0] if lines else ""
    location = lines[1] if len(lines) > 1 else ""
    return company, location


def _card_of(anchor: Tag) -> Tag:
    """The smallest ancestor that holds more text than the title link itself."""
    title = anchor.get_text(" ", strip=True)
    node = anchor
    while isinstance(node.parent, Tag) and node.parent.name not in ("body", "html", "[document]"):
        node = node.parent
        if len(node.get_text(" ", strip=True)) > len(title) + 3:
            return node
    return node


def parse_linkedin_alert(html: str) -> list[AlertOffer]:
    """Each job card once, in the alert's order, with a canonical link."""
    soup = BeautifulSoup(html, "html.parser")
    offers: dict[str, AlertOffer] = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        match = _JOB_URL_RE.search(href)
        title = anchor.get_text(" ", strip=True)
        if not match or not title or _NOISE_RE.match(title):
            continue
        job_id = match.group(1)
        if job_id in offers:
            continue
        lines = [
            line
            for line in (text.strip() for text in _card_of(anchor).stripped_strings)
            if line and line != title and not _NOISE_RE.match(line)
        ]
        company, location = _split_company_location(lines)
        if not company:
            continue
        offers[job_id] = AlertOffer(
            job_id=job_id,
            title=title,
            company_name=company,
            location=location,
            # Rebuilt from the id: no tracking parameter, and never a link the mail chose.
            url=f"https://www.linkedin.com/jobs/view/{job_id}",
        )
    return list(offers.values())
