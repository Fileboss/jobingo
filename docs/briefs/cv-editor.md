# CV editor

Implement step 2 of `docs/porting.md`: the CV editor, in two equivalent modes.

## Goal

The user enters their exhaustive CV once, either as formatted text or in a graphical form, and finds it again at every session. This is the product's first real screen: it must look good in a demo and set the tone for the whole application.

## Scope

- French CV. The data model allows for a language, but there is no interface for English yet.
- An application shell (navigation, layout) that will host future screens. Only the CV is active in it.
- Out of scope: English, identity and photo, objectives, style, template and PDF (step 3), any model call.

## Expected behaviour

- Two modes: formatted text and form. They are two views of one document, and a save from either stores the same canonical form.
- Switching mode keeps unsaved input.
- CV item ids stay stable across saves and do not appear in these two modes. A retired id is never reused.
- Diagnostics display without blocking the save, except a duplicate id. An e-mail address, phone number or profile URL detected in the CV is flagged.
- A save never overwrites a change made elsewhere: the conflict is detected and explained to the user.
- The CV persists in the database, versioned per user, and survives restarts. A new account sees a designed empty state, not an error.

## Backend

- Port from `../my-job-processor`, following the quality review in `docs/porting.md`: `src/jsh/domain/profile.py`, `cv_markdown.py`, `cv_fields.py`, `personal_data.py`, `frontmatter.py` and what they depend on, with their tests (`tests/test_profile_parser.py`, `test_cv_markdown.py`, `test_cv_fields.py`, `test_personal_data.py`).
- Read the "CV editor (M17)" invariants in the POC's `CLAUDE.md` first. The fixed point must stay true: `fields_to_markdown(parse_fields(to_clean_view(S))) == to_clean_view(S)`.
- Redesign the storage: versioned rows per `user_id` in place of the files (`services/files.py`, `profile_editor.py`). Keep the SHA-256 conflict check.
- Only one module writes the source CV, and an architecture test guarantees it, as in the POC.
- The API lets a draft be converted from one mode to the other without saving it.

## Frontend

- Before any screen, load the `frontend-design` skill and propose a visual direction. Use the `prototype` skill to show the user 2 or 3 variants of the editor, have them choose, then record the decision in `docs/decisions/`.
- Then turn that direction into design tokens and shared components, and build the shell and the editor.
- The interface is in French, works with the keyboard, and stays usable on a small screen.
- The text mode uses CodeMirror 6 if justified. Ask the user to run `pnpm add` for each dependency needed.

## Test data

Fictional only: the POC's `evals/fixtures/cv.fr.md` (persona Alex Moreau) can serve as test data. Check the screens with Claude in Chrome on this worktree's database, which is empty and fictional.

## Done when

- `make check` and `make e2e` pass, with Playwright tests covering: input in each mode, switching mode with no loss, reloading after a save, and a conflict.
- The real flow has been checked in Chrome, with the real client and API, and a screenshot has been shown to the user.
- `CLAUDE.md` (Status section) and `docs/porting.md` are up to date.
- Each agent tells the user what was done, what was left out from the POC and what remains doubtful.

Do not commit: the user reviews first.
