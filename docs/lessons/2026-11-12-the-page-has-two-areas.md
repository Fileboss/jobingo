---
date: 2026-11-12
status: active
applies_when: measuring, fitting or filling the CV's page, or reading `PageMeasure`, page counts or missing items
---

# The CV page has two areas: fit each with its own content

## What happened

On the user's real CV, the adapted page came out empty but for the summary, with « Le CV dépasse la page ». The side panel (photo, contact, long skill lines) ran off its page: being absolutely positioned, it is cut with no page added, and `verify_cv_pdf` counts the cut items. Code treated any overflow alike, so it cut the main column's ranking to fit, and since the panel still overflowed, cut it to nothing. The same confusion likely spoiled the earlier fit loops on that CV, each round seeing an overflow. No eval case had a panel too long: the fictional CVs had short skills, no photo and no contact.

## What to do instead

- Keep the two overflows apart: `PageMeasure.column_runs_over` (a page too many) and `panel_runs_over` (items cut off the panel).
- Fit the panel with the panel's content (hobbies, then the least useful skills), then the column with the ranking, each search watching its own overflow.
- Give the eval a case per area that can overflow: `panel-01` runs on a CV whose skills overrun the panel.
- When a real result looks wrong, ask what differs from the fictional cases (photo, contact, long lines) before changing the prompt.

## Prevention

`test_a_side_panel_too_long_is_cut_apart_and_the_column_still_fills` and the eval case `panel-01`.
