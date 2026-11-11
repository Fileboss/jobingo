"""How the identity's contact details are printed: a profile as its username."""

import pytest

from jobingo.domain.identity import Identity


@pytest.mark.parametrize(
    ("typed", "text", "href"),
    [
        (
            "https://www.linkedin.com/in/alex-moreau/",
            "alex-moreau",
            "https://www.linkedin.com/in/alex-moreau",
        ),
        ("linkedin.com/in/alex-moreau", "alex-moreau", "https://www.linkedin.com/in/alex-moreau"),
        ("alex-moreau", "alex-moreau", "https://www.linkedin.com/in/alex-moreau"),
        ("@alex-moreau", "alex-moreau", "https://www.linkedin.com/in/alex-moreau"),
        ("mon profil", "mon profil", ""),  # not an address: printed, not linked
    ],
)
def test_a_linkedin_profile_prints_its_username(typed: str, text: str, href: str):
    [entry] = Identity(linkedin=typed).contact_entries()
    assert (entry.kind, entry.text, entry.href) == ("linkedin", text, href)


def test_a_github_profile_keeps_the_user_not_the_page():
    [entry] = Identity(github="https://github.com/alex-moreau?tab=repositories").contact_entries()
    assert (entry.text, entry.href) == ("alex-moreau", "https://github.com/alex-moreau")


def test_the_website_drops_its_scheme_and_the_order_holds():
    identity = Identity(
        email="alex@jobingo.test",
        phone="06 00 00 00 00",
        website="https://www.alexmoreau.example/",
        github="alex-moreau",
    )
    entries = identity.contact_entries()
    assert [e.kind for e in entries] == ["email", "phone", "website", "github"]
    assert (entries[2].text, entries[2].href) == (
        "alexmoreau.example",
        "https://alexmoreau.example",
    )
    assert entries[0].href == "mailto:alex@jobingo.test" and entries[1].href == ""
