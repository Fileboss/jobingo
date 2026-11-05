# CV rendering and PDF preview

Implement step 3 of `docs/porting.md`: render the CV with the `panneau-lateral` template, and show the real PDF.

## Goal

From the exhaustive CV entered in step 2, the user chooses what goes on the page and how it is laid out, sees the real PDF update, and downloads it. Without any AI, this makes the app useful for the first time, and it is the rendering and the screen that per-offer tailoring builds on at step 4.

## Scope

- The identity (name, e-mail, phone, address, LinkedIn, GitHub) and the photo, stored apart from the CV, with a screen to edit them.
- The `panneau-lateral` template only, in French: one page, experience timeline, with its options `photo`, `panneau_competences` and `loisirs`.
- A manual selection: which experiences, bullets, education lines, skills and hobbies from the CV go on the page. The choice persists per user.
- A live preview of the real PDF, the page count, and a download.
- Out of scope: any model call, colour customization (the manifest's default colours apply), filling the page automatically, retries on overflow, other templates or a gallery, cover letters, archiving generated documents (`documents` table, step 6), the plain-text export, the signature field, English.

## Expected behaviour

- A user with no identity saved can still preview: empty identity fields are simply left out of the PDF, and the screen says what is missing.
- Identity and photo survive a restart and are replaced by a save. A photo can be removed. A photo that is not a usable JPEG or PNG, or is too large, is refused with a clear message in French.
- An uploaded photo is re-encoded: no EXIF data is kept.
- By default, everything in the CV is selected. The user can untick and tick items again, and the choice survives a reload.
- A CV item removed or added later does not break the selection: a removed id is ignored, and a new item is selected.
- With `panneau_competences` on, skills, contact details and photo are in a right-hand panel on page 1; with it off, they are in the main column. The `photo` option cannot be switched on without a photo, and `loisirs` cannot without hobbies in the CV: the screen says why.
- Each change to the selection or the options updates the preview shortly after, without a page reload, and the page count updates with it. A CV over one page gets a visible warning, but the PDF can still be previewed and downloaded: the limit informs the user and blocks nothing.
- A preview that cannot be produced (rendering failure, API down) leaves the last preview and the user's choices intact, and says so.
- The downloaded PDF has real, selectable text, in reading order, with every selected item present, and its metadata title names the document.
- No identity value and no PDF content appears in any log. Responses carrying identity, a photo or a PDF are `no-store`.

## Backend

- Port from `../my-job-processor`, following the quality review in `docs/porting.md`: `src/jsh/render/pdf.py`, `render/cv.py`, `render/verify.py` (the CV part), `render/builtin_templates/panneau-lateral/`, `domain/identity.py`, `services/photo.py`, `domain/cv_template.py`, and from `domain/cv_selection.py` only `CvOptions`, `SelectedItem`, `SelectedExperience`, a reduced `CvSelection` and what building it from a selection needs. Fields and code that only serve the model wait for step 4. Port the matching tests (`tests/test_cv_render.py`, `test_cv_templates.py`, `test_render_no_fetch.py`, `test_preview_routes.py` where it still applies).
- The template ships with the code, read-only. There is no copy in `data/` and no template editing.
- Read the POC `CLAUDE.md` invariants first: "CV options (M12)", "Colours (M15)" for the CSS variables' defaults, "Preview (M18)", and "Untrusted links and fetches" for the render's fetcher. Keep them:
  - WeasyPrint is imported only through `render/pdf.py`, which fixes the library path on Apple Silicon.
  - The render fetcher reads `data:` URIs and files under the template directory only, never the network.
  - No `position: relative` and no hyphenation or `text-transform` in the template. The panel stays the first block of the document.
  - Identity reaches the renderer as a parameter, and is never part of the stored selection.
  - The photo is embedded only when its option is on.
- Store identity and photo in their own table, apart from `cv_versions`, per `user_id`. Add the import-linter contract saying `jobingo.llm` never reaches `jobingo.domain.identity`, as `pyproject.toml` and `.claude/rules/backend.md` announce.
- Writes accept JSON only (`jobingo_api/security.py`), so the photo travels in a JSON body, base64-encoded. Keep the POC's limits on weight and pixels.
- Rendering blocks: handlers stay plain `def`.
- The new dependencies are WeasyPrint, Jinja2, Pillow and pypdf. Add Pango to the backend job in `.github/workflows/ci.yml`, as in the POC's workflow, so that CI runs the render tests instead of skipping them.
- The stylesheet names fonts that are not embedded. Say whether the rendering depends on the machine's fonts, and how much that matters for the page count.

## Frontend

- Follow the "Classeur" direction (`docs/decisions/2026-11-05-visual-direction-classeur.md`) and reuse the tokens and components in `apps/web/src/lib/ui/`. Add the new screens to `AppShell.svelte`.
- The preview is the real PDF from the server, never an HTML approximation.
- Displaying it needs care, and must be tried in real Chrome: the API's CSP sets `default-src 'none'` and `frame-ancestors 'none'`, the client's CSP in `apps/web/vite.config.ts` has no `frame-src`, and Chrome refuses PDFs in sandboxed frames. Change these only as far as needed, and agree with your peer on the change. Keep `script-src` strict.
- Headless Chromium may not display PDFs: Playwright tests can check that the preview is requested and its state shown, while the PDF's content is checked on the backend with pypdf, and its display in real Chrome.
- The selection must stay comfortable with a long CV. A user should see at once what is on the page and what is not, next to the preview.

## Test data

Fictional only: the CV in `tests/fixtures/cv.fr.md`, the identity of Alex Moreau, and a photo generated in the tests. `make pair` gives you the fictional `jobingo_pair` database and its own ports, so check your screens there with Claude in Chrome. Use your ports (`make api`, `make web`). Enter the fixture CV through the app to get something to render.

## Done when

- `make check` and `make e2e` pass, and the render tests ran rather than being skipped (`uv run pytest -rs`).
- Backend tests prove, on real PDFs: every selected item in the extracted text and in order, an unselected item absent, the page count, each option on and off, no network fetch, and no identity in the stored selection.
- Playwright tests cover: editing the identity, unticking an item with a reload, an option being unavailable, the over-one-page warning, and a failed preview.
- The real flow has been checked in Chrome, with the real client and API: enter the CV and identity, add a photo, tick and untick, switch each option, read the PDF on screen, download it. Show the user a screenshot of the screen and a rendering of the PDF.
- `CLAUDE.md` (Status section), `docs/porting.md` and `.claude/rules/` are up to date.
- Each agent tells the user what was done, what was left out from the POC and what remains doubtful.

Do not commit: the user reviews first.
