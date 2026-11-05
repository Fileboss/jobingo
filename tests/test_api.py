import json
from collections.abc import Iterator
from importlib import import_module
from inspect import iscoroutinefunction
from pathlib import Path
from pkgutil import iter_modules

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from jobingo.config import Settings
from jobingo.db import Conn
from jobingo_api import routes
from jobingo_api.main import create_app

CONTRACT = Path(__file__).resolve().parent.parent / "apps" / "web" / "openapi.json"


def test_the_account_exists_after_startup(client: TestClient, settings: Settings):
    response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json()["username"] == settings.account_username


def test_health_reports_the_database(client: TestClient):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"database": "ok"}


def test_health_is_503_when_the_database_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def fail(*args: object, **kwargs: object) -> None:
        raise psycopg.OperationalError("down")

    assert isinstance(client.app, FastAPI)
    monkeypatch.setattr(client.app.state.pool, "connection", fail)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"database": "unavailable"}


def test_an_unknown_api_path_is_a_json_404(client: TestClient):
    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"


def test_the_committed_contract_matches_the_app():
    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == create_app().openapi()


def test_routes_are_sync():
    """Handlers run blocking database and rendering code, so they belong in the threadpool."""
    modules = [
        import_module(f"{routes.__name__}.{module.name}")
        for module in iter_modules(routes.__path__)
    ]
    api_routes = [
        route for module in modules for route in module.router.routes if isinstance(route, APIRoute)
    ]
    assert api_routes
    assert [route.path for route in api_routes if iscoroutinefunction(route.endpoint)] == []


class TestLocalProtections:
    @pytest.fixture
    def writable(self, settings: Settings, conn: Conn) -> Iterator[TestClient]:
        app = create_app(settings)

        @app.post("/api/probe")
        def probe() -> dict[str, bool]:
            return {"reached": True}

        with TestClient(app, base_url="http://127.0.0.1") as test_client:
            yield test_client

    def test_another_host_is_refused(self, client: TestClient):
        # What a DNS rebinding attack looks like from the server.
        assert client.get("/api/me", headers={"Host": "evil.example"}).status_code == 400

    @pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "localhost:5173"])
    def test_local_hosts_are_accepted(self, client: TestClient, host: str):
        assert client.get("/api/me", headers={"Host": host}).status_code == 200

    @pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost:3000", "null"])
    def test_a_write_from_another_origin_is_refused(self, writable: TestClient, origin: str):
        assert writable.post("/api/probe", headers={"Origin": origin}, json={}).status_code == 403

    @pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:8000"])
    def test_a_write_from_the_client_is_accepted(self, writable: TestClient, origin: str):
        response = writable.post("/api/probe", headers={"Origin": origin}, json={})
        assert response.json() == {"reached": True}

    @pytest.mark.parametrize(
        "content_type",
        ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"],
    )
    def test_a_write_that_is_not_json_is_refused(self, writable: TestClient, content_type: str):
        response = writable.post("/api/probe", headers={"Content-Type": content_type}, content="x")
        assert response.status_code == 415

    def test_api_responses_carry_the_security_headers(self, client: TestClient):
        headers = client.get("/api/me").headers

        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"

    def test_a_refused_host_still_gets_the_headers(self, client: TestClient):
        response = client.get("/api/me", headers={"Host": "evil.example"})
        assert response.headers["x-content-type-options"] == "nosniff"


class TestServingTheClient:
    @pytest.fixture
    def with_build(self, settings: Settings, conn: Conn, tmp_path: Path) -> Iterator[TestClient]:
        build = tmp_path / "build"
        (build / "_app").mkdir(parents=True)
        (build / "index.html").write_text("<h1>client</h1>", encoding="utf-8")
        (build / "_app" / "start.js").write_text("// js", encoding="utf-8")
        (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
        app = create_app(settings.model_copy(update={"web_build_dir": build}))
        with TestClient(app, base_url="http://127.0.0.1") as test_client:
            yield test_client

    def test_a_file_is_served(self, with_build: TestClient):
        assert with_build.get("/_app/start.js").text == "// js"

    @pytest.mark.parametrize("path", ["/", "/offres", "/offres/12"])
    def test_a_client_route_gets_the_page(self, with_build: TestClient, path: str):
        assert "client" in with_build.get(path).text

    def test_an_unknown_api_path_stays_a_404(self, with_build: TestClient):
        assert with_build.get("/api/nope").status_code == 404

    def test_the_api_wins_over_the_client(self, with_build: TestClient, settings: Settings):
        assert with_build.get("/api/me").json()["username"] == settings.account_username

    def test_nothing_outside_the_build_is_served(self, with_build: TestClient):
        assert "secret" not in with_build.get("/%2e%2e/secret.txt").text

    def test_pages_cannot_be_framed(self, with_build: TestClient):
        assert with_build.get("/").headers["content-security-policy"] == "frame-ancestors 'none'"
