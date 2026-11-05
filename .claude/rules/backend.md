---
paths:
  - "apps/api/**"
  - "packages/**"
  - "tests/**"
  - "scripts/**"
---

# Backend rules

## Conventions

- Route handlers are plain `def`, because they run blocking database and rendering code in the threadpool. A test enforces it.
- Connections autocommit. Code that writes several statements opens `with conn.transaction():`, so a write is committed before the response leaves.
- A migration is a new numbered file, and an applied one is never edited. Numbers can collide between branches: the branch merged second renumbers its unmerged migration.
- Development data is kept. A migration carries existing rows forward, and no step may require resetting the main database or re-entering data. Never suggest `docker compose down -v`.
- Every business row has a `user_id`, and queries on business tables always filter on it.
- All access to the current user goes through one FastAPI dependency (`get_current_user`), so real authentication can replace it later.
- After changing an API route or schema, run `make api-types` and commit the regenerated `apps/web/openapi.json` and `schema.d.ts`. They come from that command only, including when resolving a merge conflict.

## Dependencies flow one way

`api → hitl → services → llm | connectors | render → domain`

- `llm` never reaches identity, `services`, `connectors`, `hitl`, `render` or `api`.
- Only `hitl.executor` imports the SMTP connector.
- Code carrying model output cannot write the user's source CV. Only `services.cv_editor` can, and only the API's CV routes import it (`tests/test_architecture.py`).
- Known name, e-mail and phone values are replaced by `[CANDIDAT]` before each model call. This is best effort, not a guarantee.

The layer contracts are in `pyproject.toml`. Add the SMTP contract when that module lands.

## Rendering

- Only `render/pdf.py` imports WeasyPrint: it fixes the library path on Apple Silicon. Its fetcher reads `data:` URIs and files under the template directory only.
- Identity and photo reach `render_cv` as parameters, never in the selection. The photo is embedded only when its option is on. Nothing from a render goes in a log, not even an exception's message.
- In the template's CSS: no `position: relative`, no hyphenation, no `text-transform`. The panel stays the first block of the document.
- The panel is absolutely positioned, so what runs past its page is cut with no extra page. `verify_cv_pdf` is what detects it, and `X-Missing-Items` tells the client. Render tests skip without Pango: read `pytest -rs`.
- The template embeds its font (Lato, `fonts/`), so the page count does not depend on the machine. `render_pdf` needs its `FontConfiguration` for that, and a test checks the PDF's fonts.

## Local security without authentication

No login does not mean an open server: any web page in the browser can try to call localhost, and this app can send e-mail.

- Bind `127.0.0.1` only and reject any other `Host`.
- Mutating routes accept JSON only and check `Origin`.
- `SMTP_DRY_RUN=1` by default.
- API responses are `no-store`, and those carrying identity or a PDF are never logged.
