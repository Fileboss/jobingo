from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.trustedhost import TrustedHostMiddleware

from jobingo.config import Settings
from jobingo.db import connect, create_pool, migrate
from jobingo.services.accounts import ensure_account
from jobingo_api.routes import cv, health, me
from jobingo_api.security import LocalRequestsOnlyMiddleware, SecurityHeadersMiddleware
from jobingo_api.spa import SpaFiles


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    with connect(settings.database_url) as conn:
        migrate(conn)
        ensure_account(conn, settings.account_username)
    pool = create_pool(settings.database_url)
    pool.open(wait=True)
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Jobingo",
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url=None,  # both pages load scripts from a CDN, which the CSP refuses
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings

    # The last one added is the outermost: every response gets the headers.
    app.add_middleware(LocalRequestsOnlyMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(health.router, prefix="/api")
    app.include_router(me.router, prefix="/api")
    app.include_router(cv.router, prefix="/api")

    # Absent in development, where the Vite dev server serves the client.
    if (settings.web_build_dir / "index.html").is_file():
        app.mount("/", SpaFiles(directory=settings.web_build_dir), name="client")
    return app
