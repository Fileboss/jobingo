# Porting from the POC

The POC, `../my-job-processor`, is a read-only source. Copy code into this repository file by file, and never import its git history.

**Never read:** `.env`, `evals/.env`, `data/private/`, `data/db/`.

**Never copy:** `data/`, `wiki/`, CV PDFs, `evals/results/`, `evals/.cache/`, the two templates other than `panneau-lateral`.

## Build order

Small vertical steps. To adjust as we go:

1. ~~Backend foundation~~ (done).
2. ~~Profile and CV editor, in both modes~~ (done).
3. ~~`panneau-lateral` rendering and PDF preview~~ (done).
4. ~~LLM layer, prompts and evals, with the observability page (`docs/observability.md`), then per-offer CV tailoring~~ (done). In four steps:
   1. ~~LLM layer: client interface, Anthropic client, fake client, call journal (`llm_calls`), costs, budget caps, redaction~~ (done).
   2. ~~Application log, and the observability page's Usage, Calls and Logs tabs, on the journal~~ (done).
   3. ~~`select_cv_content`: its prompts, the eval harness and suite, and the Evals tab~~ (done).
   4. ~~Per-offer CV tailoring: a server-side draft, code checks on the rewrites, the diff screen~~ (done).
5. ~~Offer intake and scoring~~ (done). In three steps:
   1. ~~Offer intake: pasted text, `extract_offer`, the `offers` table with merging, the Offers screens, its eval suite, adapting the CV from an offer~~ (done).
   2. ~~The objectives: hard filters, weights and preferences, with their editor~~ (done).
   3. ~~Scoring: hard filters in code, `score_offer` per criterion, the global score in code, its eval suite~~ (done).
6. ~~Application tracking and cover letters~~ (done). In two steps:
   1. ~~Applications: created from an offer or by hand, a timeline of events, the status derived from it, follow-ups, contact, soft delete~~ (done).
   2. ~~Cover letters: a letter template, `draft_letter`, code checks per slot, a review screen, the PDF, its eval suite~~ (done).
7. Mail, drafted replies and approval queue. In four steps:
   1. ~~Reading mail: IMAP connector, stored messages, LinkedIn alerts read in code, the Courrier screen~~ (done).
   2. ~~`classify_message` and its eval suite, linking a message to an application, suggestions confirmed by a click~~ (done).
   3. ~~The approval queue and its one executor, the SMTP connector, dry run by default~~ (done).
   4. ~~`draft_reply` and its injection eval suite~~ (done).
8. Demo: fictional seed, screenshots, README.

## What to bring over

- `domain`, `services`, `llm`, `render`, `hitl`, `connectors`, with their tests. The POC's `CLAUDE.md` records invariants that were each a bug once: read the relevant ones before porting a module, and keep them.
- **All prompts**, since they were evaluated, and the eval suites with their fictional cases.
- **No eval results.** Every score and every model choice (model, thinking, effort) gets measured again here. The POC's settings are starting hypotheses. Do not publish a score that was not measured in this repository.
- The application log and journal (`jsh.logs`, redacting filter, `services/monitoring.py`), with the LLM layer. The Jinja pages become the observability page.

## Quality review at each port

Copying is not enough, and the POC's quality is not assumed. For each module:

1. Read it and flag what is unclear, dead or overbuilt, such as unused columns or old prompt-version branches.
2. Bring it up to this repository's checks (`ruff format`, which was not clean in the POC, and pyright). Replace any real name in comments and test data with a fictional one: the POC was private, and this repository is public.
3. Port its tests and make sure they pass here.
4. Report what changed and what remains doubtful.

## What to redesign rather than copy

Client-server breaks these:

- Tasks and proposals held in memory → persisted jobs and drafts, which survive a restart.
- CV diff state in hidden form fields → a server-side draft with its own API.
- Files in `data/profile/` → versioned rows per user (`cv_versions`, done for the CV; objectives and style remain). Markdown stays the CV's canonical format.
- Routes, Jinja templates, HTMX and polling → JSON API, Svelte client and SSE.

## Template scope

Only `panneau-lateral`: strictly one page, French format, experience timeline, with optional photo and optional right-hand panel. Keep its template and manifest options generic enough to allow others later.

What step 3 left in the POC, for the step that needs it:

What step 4.1 left in the POC: `journal.find_reusable_call` and `reuse_or_run_task`, for 4.4 and the CV proposal only. Step 4.2 replaced the POC's JSON-lines log file with the `app_events` table.

After step 7, on the user's request (2026-11-10):

- Merging close CV items was tried and dropped: prompts v6 to v8 asked Sonnet 5.5 to merge two complementary bullets when the page lacked room, and measured on 2026-11-10 (10/11, 9/11, 10/11 on 11 cases) it never merged where a case required it, leaving a bullet out instead. The user settled that the source CV is theirs to write well: v5 ships, and the merge code, cases and prompts are gone.
- An offer has two scores, fit and salary, never mixed; the global score and the salary weight are gone (migration 0017).
- Each application has the user's own rating, 1 to 5 stars (migration 0018).
- An adapted CV belongs to an application (`cv_drafts.application_id`, migration 0019, which moved each draft to the live application of its offer). It is made from the application's page only, for a spontaneous one from the role, the company and the notes; the offer pages, the « Adapter » screen and its pasted-offer route are gone.
- « Projets personnels » is a known section, one line per project (`project-` ids, alias `R` for the model), printed under the experiences, at most 3 in a proposal. `select_cv_content` v6 knows it; the eval CV has two projects. A CV saved while the section was unknown holds its lines without ids: the editor flags it (`needs_save`) and one save carries them forward, since only a human save writes the source CV.

What step 7.4 changed or left:

- `draft_reply` ships as the POC's v4, the version in service: a missing fact becomes the canonical `[À COMPLÉTER : …]` marker, whose labels the system prompt lists verbatim (a test keeps them equal to `domain/placeholders.py`). Its 6 cases and the 15 injection cases are ported, every domain rewritten to `.example`. Neither suite is measured here yet: run `make eval ARGS="--task draft_reply"` and `--task injection`.
- The injection suite keeps the POC's policy: every case must pass (threshold 1.0), across `classify_message`, `extract_offer` and `draft_reply`, and no action may be queued. It sets the fictional identity itself, so the other suites' requests, and their cached answers, are unchanged.
- A draft is not stored: it fills the composer, the user edits it, and the queue refuses any gap left (`find_placeholders`, which also catches `[CANDIDAT]` and other forms). The action keeps the call it was drafted from (`pending_actions.llm_call_id`).
- A test now checks the rule that a prompt example is never an eval case: `draft_reply` v4 is the first shipped prompt with examples.
- Not ported: drafting a first message to a contact (the POC's stand-in message built from the offer), and the style guide's word limit, which `StyleGuide` does not carry yet.

What step 7.3 changed or left:

- The queue keeps the POC's design: a payload frozen at proposal with its SHA-256, approval of the hash on screen, an atomic claim (`approved` to `sending`) so a double click sends once, the hash checked again by the executor, a failed send retried as approved with the same Message-ID. Postgres triggers forbid changing a payload and deleting an action.
- Approving sends at once, in the same request: one click, « Valider et envoyer ». There is no worker yet.
- Attachments are rendered once at proposal and archived in `documents` (bytes in Postgres, not files under `data/`), never changed nor deleted; the executor checks each one against its SHA-256. The CV attached is the latest draft adapted to the application's offer, else the CV page; a CV over one page or a letter that could not be downloaded is refused.
- A dry run (`SMTP_DRY_RUN=1`, the default) builds the message, keeps its exact bytes (`pending_actions.eml`, downloadable) and sends nothing; it records no `message_sent` event, since nothing left. A real send to the local Mailpit is safe for a demo: set `SMTP_DRY_RUN=0` with the default mail settings.
- The sender's name comes from the identity, put in by code at proposal: the payload never reaches the model. Plain SMTP is refused beyond loopback, like IMAP.
- Not ported: the POC's expiry of old proposals (no scheduler), the stand-in message for writing to a contact, the signature (`Identity` has none yet), and the placeholder check on drafts, which comes with `draft_reply` (7.4). Sent messages are not stored in `messages`: the action is the record.

What step 7.2 changed or left:

- `classify_message` ships as the POC's v2, the version in service (its v3, with examples, scored lower). Its 50 fictional cases are ported, every domain rewritten to `.example`, and the POC's 0.90 threshold is kept as a policy. Measured on 2026-11-09: 49/50 messages, 11/11 interview dates, 0.0036 $ for the run. The one miss, `int-10` (a client wanting a call, with no time set), went to `recruiter_other`: the user can still tie it and add the interview by hand.
- Rules come before the model: a message with `List-Unsubscribe` (a newsletter) or from a blocked sender is hidden without a call, so less mail reaches the model. The cost: another sender's alert in the inbox is hidden as a newsletter; a dedicated alert folder avoids it, and restoring a hidden message sends it to the model at the next sync.
- The category is the model's verdict alone: a message a rule hid has none. `other` is hidden; `offer` goes through `extract_offer`, its offers pointing to the message; the three others are matched to an application.
- Matching, in code and in this order: the thread of a message already tied to an application, the application's contact address (there is no `companies` table, so no website domain), then a company name above 90 % similarity. An offer is never matched: it is a new job, not news of an application.
- Being tied records `message_received`, the one event added without a click. A refusal or an interview is a suggestion, stored on the message, that becomes an event only when the user confirms it; dismissing it is logged with the call id. Events carry their `message_id` and move with the message; untying removes them, and an accepted suggestion goes back to pending.
- The POC's `handled` and `read_at` flags are not ported: « À traiter » is computed on the client from the suggestion, the category and the link.

What step 7.1 changed or left:

- The IMAP connector uses the standard library's `imaplib`, not `imap-tools`: EXAMINE and BODY.PEEK make it read-only, and plain IMAP is refused beyond loopback, so a password never crosses the network in clear. Tests read a real GreenMail mailbox per test, not a fake source.
- The cursor is kept per mailbox and folder (`mail_folders`), so switching from the local server to Gmail starts fresh. The first sync reads the last 30 days only, then at most 200 messages per folder and per sync.
- Alerts: a LinkedIn sender whose HTML holds job cards is read in code, in any folder; any other message in a dedicated alert folder waits for `extract_offer`. With the alert folder equal to the inbox, other senders' alerts are only found once classification lands (7.2).
- The POC's thread and in-memory sync status are not ported: the request waits for the sync. Classification, blocked senders, the newsletter rule and matching to applications came with 7.2.
- The HTML part is stored for the alert reader and never sent to the client: the screen shows the text only.

What step 6.2 changed or left:

- One letter template, `lettre-classique`, shipped with the code like the CV template: a manifest declaring the slots, an HTML body and a stylesheet with the same embedded font. The POC's user-editable Markdown templates and their parser are not ported, nor markdown-it.
- `draft_letter` ships as v4: the POC's v3 without the page-overflow retry and the single-slot regeneration, which this app does not offer yet. Its 6 fictional cases are ported. Measured on 2026-11-07: 6/6 letters with no refused slot, 0.067 $ for the run. The system part carries the offer and the notes, so it changes from one application to the next: every case paid a cache write and none read it. A cache only pays here when one application gets several letters.
- The POC's checks hold: a slot over its word limit, with a figure absent from its declared sources, or with a forbidden phrase is refused and comes back empty, the proposal and the reason beside it; an added proper noun is flagged. The user may write or adopt anything: the download is blocked only by an empty slot, one over its limit, or a second page.
- Company notes are a field of the application, a source of the `motivation` slot. The letter draws on the CV adapted to the offer when there is one, else on the whole CV.
- No archive of sent documents with their SHA-256 yet: it comes with sending, at step 7.

What step 6.1 changed or left:

- `domain/applications.py` keeps the POC's rules: the status is derived from the events in date order, a message never takes an application back from the interview nor reopens a closed one, a follow-up is due a week after sending if nothing happened, deleting only hides. One live application per offer is a unique index.
- No `companies` table, no company preference or slug yet: the company is a name on the application. Company notes, which the letter uses as a source, come with step 6.2.
- Follow-ups are computed and shown, not written as events; the POC's `ensure_follow_ups` and its scheduler are not ported.
- Mail events (`message_id`, moving events between applications) come with step 7.

What step 5.3 changed or left:

- `score_offer` ships as the POC's v1, with its 15 hand-ranked fictional cases and the POC's 0.85 rank-correlation threshold, kept as a policy. Measured here on 2026-11-07: 0.948 on Haiku 5.5. `extract_offer` v2 measured 103/103 fields the same day.
- The POC's single `status` is split in two: `state` (new, scored, filtered), set by scoring, and `decision` (shortlisted, dismissed), set by the user only. Scoring cannot walk back a decision by construction.
- Every score is kept (`offer_scores`) with the weights, the objectives' hash and the CV version it was computed from, so a stale score is shown as such and can be refreshed in one click.
- Offers are scored right after intake. A failed scoring keeps the offers and says so; a batch stops at the first failed call.

What step 5.2 changed or left:

- The POC's `objectifs.md` (YAML front matter and a free-text body) becomes an `objectives` row edited in a form: filters and weights are structured and validated, the preferences stay free text.
- `apply_hard_filters` keeps the POC's rules: a known value that fails eliminates, an unknown one is only flagged, comparisons ignore case (and now accents). The Objectives screen previews them on the offers received.
- Weights go from 0 to 5; the POC's were unbounded floats.

What step 5.1 changed or left:

- `extract_offer` ships as v2, the POC's version in service (its v3 cost 23 % more for the same score). Its contract and remote values are `Literal`s on `ExtractedOffer` itself: there are no older answers to stay compatible with.
- Offers arrive only by pasting for now. Mail alerts (`linkedin_alert.py`, IMAP) come with step 7, France Travail is not planned.
- No status yet: it comes with scoring, with the rule that scoring never walks back a status the user set.
- The POC's intake ran in a thread with polling; here the request waits for the call, a few seconds on the fast tier.

What step 4.4 changed or left:

- A draft (`cv_drafts`) stores the checked proposal unchanged, as the trail, and the user's choices apart. It replaces the POC's diff state in hidden form fields and its in-memory proposals, so `reuse_or_run_task` is not ported: a proposal is stored once, and a new one is a new draft.
- The offer is pasted text (`OfferInput`) until step 5 gives offers a table; the draft then gains an `offer_id`.
- The options come from the CV page and stay editable on the draft. Filling the page and developing an item (`elaborate_item`) are not ported.
- The POC's page-overflow retry is not kept: an adapted CV fills its page by ranking (2026-11-12). The model ranks, in one call, the main column's elements (experiences, bullets, projects, education) it would show for the offer, most useful first, and picks skills and hobbies as before (prompt v11, answer `CvRanking`). Code takes the ranking in order (`proposal_at`, then the usual `review_proposal`) and keeps the longest head that fits the page, found by a binary search over real renders (`cv_drafts.fit_ranking`, `RenderedPdf.fill` measuring how far down the page the text goes). The rest is left out by code, said as such on the diff screen (`DiscardedItem.by_code`). A page under 80 % gets a warning: the model ranked too little, or the next element did not fit.
- How it got there, measured on 2026-11-12 (Sonnet 5.5): a loop asking the model again until the page was 80 % to 100 % full (v7 to v10) never held. Told a share to remove, the model removed about 70 %; told a number of characters, it overshot both ways (asked for 2 400, it gave 1 158, then 3 240), and v10 had 1 page case in range out of 5. Filling the page back in code with what the model had left out was refused by the user. The suite's page cases (`fit-*`, `fill-*`) run on `evals/fixtures/cv-verbeux.fr.md`, a CV longer than a page. v11 (the ranking) scored 9/13 for 0.11 $: every page fitted, 3/5 in range, two short at 78.5 % and 79.96 %, and two cases filled with an off-topic Java bullet the case excludes. v12 completes with true, neutral elements and never off-topic ones, and asks to rank beyond the page: 8/13, three off-topic bullets kept, the model counting them as general experience. v13 makes the model sort each element into one of two ranked lists, `sert_l_offre` then `complement`, or the discarded ones: 10/13, four of five pages in range, its misses unrelated experiences put in `complement`. The user then judged the rule too strict: with room, every professional experience goes on the page. v14 ranks every experience, an unrelated one in `complement`, and the suite's `must_drop` became `not_serving`: such an element may complete the page, never be ranked as serving the offer. The diff screen marks what is there « en complément ». Measured on 2026-11-12: 13/13, the five page cases in range in one call each, 52 elements shortened and no rewrite refused, 0.11 $ for the run. The user's real CV then came out empty: its side panel ran off its page, and code cut the main column for it. The panel and the column now fit apart (`fit_ranking`: the panel's hobbies then least useful skills first, then the column), and the suite gained `panel-01`, on `evals/fixtures/cv-panneau.fr.md`, whose skills overrun the panel: 14/14 with it, measured on 2026-11-12. The template's cap of four experiences was then lifted (it cut a recent role off a page with room); measured again: 13/14, `fit-01` at 78 % with a ranking a little short. The user kept v14 as it is.

What step 4.3 changed or left:

- `select_cv_content` ships as **v5**: the POC's v4 without the `options` the model proposed, since the user sets them before the call, and without the page-overflow retry (`OverflowHint`), which 4.4 decides on. Its score is to be measured here: no POC figure carries over.
- Prompts v1 to v3 of this task stay in the POC: they were superseded, and the decision to port every prompt is applied to the versions in service, each with its task.
- No style editor yet: the app sends an empty style, the eval sends `evals/fixtures/style.md`. `domain/style.py` is ready for it.
- The eval harness keeps the POC's design (own key, cache keyed on the exact request, spending cap, re-grade from the cache keeps the measured spend) on a throwaway Postgres database. `--prompt-version`, the LLM judge and the README scores table are not ported: the observability page shows the results.

- `domain/cv_selection.py`: everything serving the model (proposals, `validate_rewrite`, `short_ids`, the trail fields of `SelectedItem`) waits for step 4, as do the manifest's `sections` limits, and `domain/chronology.py`. This repository's `CvSelection` is built from the CV and the ids left out, in CV order.
- `domain/colors.py` and the manifest's `colors`/`contrast`: no colour customization yet, so the stylesheet's `:root` is the one source of the defaults.
- `render/cv.py`: the plain-text export. `render/verify.py`: the letter check. `Identity.signature`.
