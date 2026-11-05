"""Protections for a server with no login, which any page in the browser can try to call."""

from collections.abc import Collection

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class LocalRequestsOnlyMiddleware:
    """Refuse writes coming from another site.

    A browser always sends `Origin` on a cross-site write; a request without it
    comes from a local tool, not from a web page. Refusing anything but JSON also
    rules out the forms and simple requests a browser sends without a preflight.
    """

    def __init__(self, app: ASGIApp, allowed_origins: Collection[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        content_type = headers.get("content-type")
        if origin is not None and origin not in self.allowed_origins:
            response = JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        elif content_type is not None and not content_type.startswith("application/json"):
            response = JSONResponse({"detail": "JSON only"}, status_code=415)
        else:
            await self.app(scope, receive, send)
            return
        await response(scope, receive, send)


class SecurityHeadersMiddleware:
    """Set headers on every response.

    The client's own CSP is in its HTML, written by SvelteKit with the hashes of
    its inline scripts (see `vite.config.ts`). A header cannot repeat `script-src`:
    a browser enforces every policy it receives, so it would block those scripts.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_api = scope["path"].startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                if is_api:
                    headers["Content-Security-Policy"] = (
                        "default-src 'none'; frame-ancestors 'none'"
                    )
                    headers["Cache-Control"] = "no-store"
                else:
                    headers["Content-Security-Policy"] = "frame-ancestors 'none'"
            await send(message)

        await self.app(scope, receive, send_with_headers)
