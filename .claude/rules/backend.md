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

The layer contracts are in `pyproject.toml`. Add the identity and SMTP contracts when those modules land.

## Local security without authentication

No login does not mean an open server: any web page in the browser can try to call localhost, and this app can send e-mail.

- Bind `127.0.0.1` only and reject any other `Host`.
- Mutating routes accept JSON only and check `Origin`.
- `SMTP_DRY_RUN=1` by default.
- API responses are `no-store`, and those carrying identity or a PDF are never logged.
