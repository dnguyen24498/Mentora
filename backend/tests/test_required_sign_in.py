"""The platform is locked behind a sign-in, and a password is what signs you in (V0-023).

These tests exercise the **shipped default** configuration — no development tenant
shortcut — so they prove the properties the task's acceptance criteria name:

* with default settings a request carrying only a tenant header is refused with
  ``401 SESSION_REQUIRED`` on every guarded route, and only the authentication
  surface answers otherwise;
* a fresh installation creates its first administrator with a password — the
  one-shot bootstrap stays available (its own switch, default on) — and signs in
  with it;
* an administrator creates an account with a password, and the holder changes their
  own;
* a wrong current password is refused **without** invalidating the caller's session,
  and a change revokes the account's other live sessions while keeping the caller's.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import Settings

TENANT = "university-001"
HEADER = {"X-Institution-Id": TENANT}
PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "a-brand-new-passphrase"


@pytest.fixture
def client(settings):
    """The **default** (locked) settings: no development tenant shortcut."""

    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _login(client, email: str, password: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"institution_id": TENANT, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _admin(client, email: str = "root@uni.test") -> dict:
    """Bootstrap the tenant's first administrator and sign in — what an operator does."""

    boot = client.post(
        "/auth/bootstrap-admin",
        json={"institution_id": TENANT, "email": email, "password": PASSWORD},
    )
    assert boot.status_code == 201, boot.text
    assert boot.json()["credential_set"] is True
    return _login(client, email, PASSWORD)


# -- the default is locked -----------------------------------------------------------


def test_the_shipped_configuration_requires_a_session(monkeypatch):
    """``dev_tenant_header`` is off unless it is explicitly turned on (V0-023)."""

    assert Settings(database_path="m.db", object_root="o").dev_tenant_header is False
    assert Settings(database_path="m.db", object_root="o").admin_bootstrap is True

    # …and the environment default agrees, so a deployment that sets nothing is locked.
    monkeypatch.delenv("MENTORA_DEV_TENANT_HEADER", raising=False)
    monkeypatch.delenv("MENTORA_ADMIN_BOOTSTRAP", raising=False)
    from_env = Settings.from_env("/tmp/mentora-required-sign-in")
    assert from_env.dev_tenant_header is False
    assert from_env.admin_bootstrap is True


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("get", "/courses", {}),
        ("post", "/courses", {"params": {"title": "x"}}),
        ("get", "/classes", {}),
        ("get", "/classes/abc", {}),
        ("post", "/classes", {"params": {"course_id": "abc"}}),
        ("get", "/accounts", {"params": {"role": "student"}}),
        (
            "post",
            "/accounts",
            {"json": {"email": "a@b.test", "role": "student", "password": PASSWORD}},
        ),
        ("patch", "/accounts/abc", {"json": {"display_name": "x"}}),
        ("delete", "/accounts/abc", {}),
        ("get", "/renderer", {}),
        ("post", "/artifacts/abc/compile", {}),
        ("get", "/artifacts/abc/renders/0", {}),
        ("get", "/course-versions/abc/publication", {}),
        ("get", "/publications/abc", {}),
        ("get", "/auth/me", {}),
        (
            "post",
            "/auth/password",
            {"json": {"current_password": PASSWORD, "new_password": NEW_PASSWORD}},
        ),
    ],
)
def test_every_guarded_route_needs_a_session(client, method, path, kwargs):
    """The tenant header authorizes nothing: there is no principal (``401``)."""

    response = getattr(client, method)(path, headers=HEADER, **kwargs)

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert response.json()["error"]["issue_code"] == "SESSION_REQUIRED"


def test_only_the_authentication_surface_answers_without_a_session(client):
    """Health, sign-out and the first-administrator bootstrap are the exceptions."""

    assert client.get("/health").json() == {"status": "ok"}
    # Signing out with nothing to revoke is not an error — it must never fail.
    assert client.post("/auth/logout").json() == {"revoked": False}
    # A sign-in *attempt* answers with a credential refusal, not a session refusal.
    refused = client.post(
        "/auth/login",
        json={"institution_id": TENANT, "email": "nobody@uni.test", "password": PASSWORD},
    )
    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert refused.json()["error"]["issue_code"] == "INVALID_CREDENTIALS"


# -- a password signs you in ---------------------------------------------------------


def test_the_first_administrator_is_created_with_a_password_and_signs_in(client):
    """A locked deployment can still bootstrap its first account (V0-023)."""

    headers = _admin(client)
    me = client.get("/auth/me", headers=headers).json()
    assert me["principal"]["authenticated"] is True
    assert me["principal"]["role"] == "institution_admin"
    # The client can see the mechanism is a labelled stand-in, not a decided one.
    assert me["authenticator"]["kind"] == "DEVELOPMENT_MOCK"
    assert me["admin_bootstrap"] is True
    assert me["development_shortcut"] is False

    # A wrong password is refused, and identically for a known and an unknown subject.
    wrong = client.post(
        "/auth/login",
        json={"institution_id": TENANT, "email": "root@uni.test", "password": "not-it-at-all"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["issue_code"] == "INVALID_CREDENTIALS"


def test_a_short_password_is_refused_when_an_account_is_created(client):
    headers = _admin(client)

    refused = client.post(
        "/accounts",
        json={"email": "ana@uni.test", "role": "student", "password": "short"},
        headers=headers,
    )

    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["issue_code"] == "CREDENTIAL_TOO_WEAK"
    # Nothing was written: there is no account to sign in as.
    assert client.get("/accounts", params={"role": "student"}, headers=headers).json()[
        "accounts"
    ] == []


def test_an_administrator_creates_a_password_and_the_holder_signs_in(client):
    admin = _admin(client)

    created = client.post(
        "/accounts",
        json={"email": "ana@uni.test", "role": "student", "password": PASSWORD},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    assert created.json()["credential_set"] is True

    student = _login(client, "ana@uni.test", PASSWORD)
    assert client.get("/auth/me", headers=student).json()["principal"]["role"] == "student"


def test_the_bootstrap_can_be_turned_off_independently_of_the_shortcut(settings):
    """``admin_bootstrap`` is its own switch, so the two do not move together."""

    locked = Settings(
        database_path=settings.database_path,
        object_root=settings.object_root,
        dev_tenant_header=False,
        admin_bootstrap=False,
    )
    with TestClient(create_app(locked)) as hardened:
        refused = hardened.post(
            "/auth/bootstrap-admin",
            json={"institution_id": TENANT, "email": "root@uni.test", "password": PASSWORD},
        )
    assert refused.status_code == 404, refused.text
    assert refused.json()["error"]["issue_code"] == "BOOTSTRAP_DISABLED"


# -- changing your own password ------------------------------------------------------


def test_a_wrong_current_password_is_refused_without_invalidating_the_session(client):
    admin = _admin(client)

    refused = client.post(
        "/auth/password",
        json={"current_password": "not-my-password", "new_password": NEW_PASSWORD},
        headers=admin,
    )

    assert refused.status_code == 401, refused.text
    assert refused.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert refused.json()["error"]["issue_code"] == "INVALID_CREDENTIALS"
    # The session is still the caller's: a mistyped current password is not a sign-out.
    assert client.get("/auth/me", headers=admin).status_code == 200
    # And the password did not change.
    assert _login(client, "root@uni.test", PASSWORD)


def test_changing_a_password_revokes_the_other_sessions_and_keeps_the_callers(client):
    admin = _admin(client)
    # A second tab, same account: it must stop working when the password changes.
    other_tab = _login(client, "root@uni.test", PASSWORD)

    changed = client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=admin,
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["changed"] is True
    assert changed.json()["sessions_revoked"] == 1, "the other tab is revoked"
    # The caller's own session survives; the other tab does not.
    assert client.get("/auth/me", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=other_tab).status_code == 401
    # The old password is refused; the new one signs in.
    old = client.post(
        "/auth/login",
        json={"institution_id": TENANT, "email": "root@uni.test", "password": PASSWORD},
    )
    assert old.status_code == 401
    assert _login(client, "root@uni.test", NEW_PASSWORD)
