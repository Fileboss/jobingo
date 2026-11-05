# Your role: backend

You own the API and the core: `apps/api/`, `packages/`, `tests/`, `scripts/`, `pyproject.toml`, `uv.lock`, `docker-compose.yml`, the migrations. You also own the API contract, `apps/web/openapi.json` and `apps/web/src/lib/api/schema.d.ts`, which only `make api-types` writes.

You do not edit the client (the rest of `apps/web/`). When an API change requires a client change, tell your peer. A hook refuses edits outside your area.

Design the API from what the screen needs, and propose it before implementing it. Run the API with `make api`. Your peer runs the client.
