---
date: 2026-11-13
status: active
applies_when: changing the order, sort, search or filters of the Offres or Candidatures tables, or what they show by default
---

# The Offres and Candidatures tables sort, search and filter as in the POC

## Question

The two tables had a fixed order (applications newest first, offers by fit with a checkbox). The user asked for tables that sort and filter like the POC's (milestones M19 and M20), with the same default display.

## Decision

- **Default order, as in the POC.** Applications: the user's stars, then fit, then salary score, then company and title. Offers, which have no stars: fit, then salary score, then company and title. At each level an unknown value comes after the known ones; text ignores case and accents.
- **A header sorts.** One click ascending, a second descending, a third back to the default order, which breaks ties. Unknown values stay last in either direction. The header carries `aria-sort`.
- **A search** on every word, case and accents aside: applications on title, company and status; offers on title, company, places and contract.
- **Filters**, each removable from its tag: applications by status, minimum stars, follow-up due, and « Afficher les clôturées »; offers by status, contract and remote work.
- **Closed applications are hidden by default**, as in the POC, unless asked for or filtered on.
- **Every offer stays in the table by default.** The POC opened on its « nouvelles » tab; here the decision « All offers in one table » holds, and the status filter replaces the tabs.
- **The state lives in the address** (`?tri=…&sens=…&q=…` and the filters): shareable, and « précédent » works. Nothing is stored.
- Sorting and filtering run in the client, on the full lists the API already returns, in `lib/tables/table.ts`. Each application carries its offer's fit, salary score and range for that.

## Why

The POC's tables were the working view the user relied on; the default order puts what they rate highest first without any order typed by hand.
