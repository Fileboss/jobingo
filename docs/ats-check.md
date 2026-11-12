# The ATS check

What a recruiting tool reads from a CV the app renders, by two parsers run locally. A development tool, off by default: not part of the app, the tests or CI.

## Running it

```sh
make ats-up                      # Tika on :9998, Affinda on :8090 (first start: a 1.6 GB image)
make ats                         # the fictional CV (Alex Moreau)
make ats ARGS=path/to/cv.pdf     # any PDF, such as a downloaded draft
make ats ARGS="cv.pdf --text"    # the whole text as read; --json for the parser's whole answer
make ats-down
```

The report prints the start of the text in reading order, then the fields an ATS would fill: name, email, phone, place, links, summary, each experience with its dates, education, projects, skills and languages, with `NON TROUVÉ` where a field is missing. Nothing is written to disk.

## The two parsers

- **Apache Tika** (`apache/tika`, Apache 2.0): text extraction, the first step of many parsing pipelines. It shows the order in which the text is read, the characters as decoded, and what the side panel does to the reading order.
- **Affinda's resume parser** (`affinda/resume-parser`, proprietary): a commercial parser, of the kind ATS vendors build on, run as a local container. It returns the same structured answer as Affinda's cloud API. Without a licence it runs in evaluation mode, 1 000 parses counted in the `affinda-data` volume; a free trial licence (affinda.com) goes in `.env` as `AFFINDA_LICENSE_TOKEN`. Its image is built for x86 only and is emulated on Apple Silicon.

Neither is the parser of a given ATS: Workday, Taleo and others are closed services. A field these two find is likely found elsewhere; a field they miss is worth fixing.

## Privacy

A real CV holds personal data, so the parsers must not be able to send it anywhere. `docker-compose.yml` puts them on a network with no route out (`internal: true`); the only way in is the `ats-gateway` (nginx, `docker/ats/gateway.conf`), bound to 127.0.0.1. Checked on 2026-11-12: from that network, neither an outside address nor DNS answers. Affinda's documentation also states no telemetry and an offline licence check.

## First findings (fictional CV, 2026-11-12)

Read well: name, email, phone, place, links, the three positions with their companies and dates; extraction quality `high`. Read badly: education found five times for three lines, one degree cut short; no personal project recognised; skills made up from bits of sentences.

## On a real CV (2026-11-12)

The user ran it on their own CV, which stayed on their machine; the examples below are made up. Read well: identity, contact, links, every position with its company and dates, certifications as certifications, projects; extraction quality `high`. What it taught:

- A justified summary came out with doubled spaces in Tika's text: the template no longer justifies text (`test_no_text_is_justified`).
- Parentheses and guillemets in a line cut it short: a degree written « Master d'informatique (« parcours Données ») » would end at « (« parcours », and a skill group « Cloud (AWS), files de messages (Kafka) » breaks at each parenthesis. Short lines without parentheses parse whole: a matter for the source CV.
- A section the page left out (languages, cut from the panel) is simply not found.
- Affinda reads each education line twice: once whole (degree, school, years), once partly, sometimes with a neighbouring line's year. Tried on the fictional CV with certifications before or after degrees, in a section of their own, without the panel, as a plain list and on two lines: the duplicate stays in every layout, so it is the parser's, not the template's. Other parsers may not do it.
