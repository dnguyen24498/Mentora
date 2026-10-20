"""Single-origin mode serves the built SPA, including its client-side routes.

The Teacher Studio lives at ``/studio/{artifactId}`` (a real page you can open in
its own tab), so the backend that serves ``frontend/dist`` must answer that URL
and any other extension-less path with the app shell — while still serving real
assets, still 404ing a missing asset, and still keeping the JSON API's own 404s.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import Settings
from app.db.database import init_db

ARTIFACT = "1e4c06bc-f29e-4ba4-9b39-b0b2cf5f4f1e"


@pytest.fixture
def dist(tmp_path):
    """A minimal stand-in for `npm run build` output."""

    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(
        "<!doctype html><html><body><div id=root>SHELL</div></body></html>", encoding="utf-8"
    )
    (root / "assets" / "index-abc123.js").write_text("console.log('bundle')", encoding="utf-8")
    return root


@pytest.fixture
def spa_client(tmp_path, dist):
    settings = Settings(
        database_path=tmp_path / "mentora.db",
        object_root=tmp_path / "objects",
        frontend_dist=dist,
        # V0-023: the shortcut is off by default; the pre-identity API suites opt in.
        dev_tenant_header=True,
    )
    init_db(settings.database_path)
    with TestClient(create_app(settings)) as client:
        yield client


def test_root_serves_the_app_shell(spa_client):
    response = spa_client.get("/")
    assert response.status_code == 200
    assert "SHELL" in response.text


def test_a_deep_link_to_a_client_route_serves_the_app_shell(spa_client):
    response = spa_client.get(f"/studio/{ARTIFACT}")
    assert response.status_code == 200, response.text
    assert "SHELL" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_an_unknown_client_route_serves_the_app_shell(spa_client):
    """The SPA owns routing, so it renders its own not-found view."""

    response = spa_client.get("/nope/deep/link")
    assert response.status_code == 200
    assert "SHELL" in response.text


def test_a_real_asset_is_still_served_as_itself(spa_client):
    response = spa_client.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "bundle" in response.text


def test_a_missing_asset_still_404s(spa_client):
    """Rewriting a script request to HTML would break the browser, not help it."""

    assert spa_client.get("/assets/index-stale.js").status_code == 404
    assert spa_client.get("/favicon.ico").status_code == 404


def test_api_routes_keep_precedence_over_the_spa_mount(spa_client):
    assert spa_client.get("/health").json() == {"status": "ok"}


def test_the_api_keeps_its_own_json_404(spa_client):
    """A missing artifact is an API 404, not the app shell."""

    response = spa_client.get(
        "/artifacts/00000000-0000-0000-0000-000000000000",
        headers={"X-Institution-Id": "university-001"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
