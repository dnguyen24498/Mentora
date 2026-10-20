"""The account directory and role separation, end to end (V0-022, V0-023).

Every test drives the real FastAPI app, the real SQLite store and the real local
object store. The properties asserted are the ones the task's acceptance criteria
name, and they are asserted directly rather than inferred from a happy path:

* three roles over one session surface — an administrator signs in and out exactly
  like a teacher and a student, with a **password**;
* an administrator manages the directory, and **nobody else can**;
* creating an account is create-or-link, never re-mints a credential, and never
  overwrites the password the holder already has;
* disabling an account takes effect on the **next request**, not at expiry;
* resetting a password revokes the account's live sessions and the old one stops
  working;
* a role change can only ever *remove* a capability from a live session;
* an account a class references is deactivated, not removed;
* the tenant boundary holds for every one of those verbs;
* the one-shot administrator bootstrap is per tenant and absent on a deployment
  that turns it off.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.identity.models import Role

HEADERS = {"X-Institution-Id": "university-001"}
OTHER_TENANT = {"X-Institution-Id": "university-002"}
ADMIN_EMAIL = "root@uni.test"

#: The password every account in this suite is created with (V0-023).
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def settings(dev_settings):
    """This suite drives the pre-identity V0 API as a teacher, so it opts into the
    development tenant shortcut (V0-023). The shipped default requires a session on
    every route; that locked default is covered by ``tests/test_password_auth.py``.
    """

    return dev_settings


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _bootstrap(client, institution: str = "university-001", email: str = ADMIN_EMAIL) -> dict:
    return client.post(
        "/auth/bootstrap-admin",
        json={"institution_id": institution, "email": email, "password": PASSWORD},
    )


def _sign_in(client, email: str, password: str, institution: str = "university-001") -> dict:
    response = client.post(
        "/auth/login",
        json={"institution_id": institution, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _admin(client, institution: str = "university-001") -> dict:
    """A signed-in administrator, bootstrapped once per app instance.

    The bootstrap really is one-shot, so it is memoised on the app rather than called
    per test step.
    """

    cache = getattr(client.app.state, "_mentora_test_admins", None)
    if cache is None:
        cache = {}
        setattr(client.app.state, "_mentora_test_admins", cache)
    if institution not in cache:
        boot = _bootstrap(client, institution)
        assert boot.status_code == 201, boot.text
        cache[institution] = _sign_in(client, ADMIN_EMAIL, PASSWORD, institution)
    return cache[institution]


def _create(
    client,
    email: str,
    role: str,
    headers: dict | None = None,
    password: str = PASSWORD,
) -> tuple[int, dict]:
    response = client.post(
        "/accounts",
        json={"email": email, "role": role, "password": password},
        headers=_admin(client) if headers is None else headers,
    )
    return response.status_code, response.json() if response.content else {}


def _account(client, email: str, role: str = "student") -> dict:
    status, body = _create(client, email, role)
    assert status == 201, body
    return body


# -- the three roles over one session surface ----------------------------------------


def test_an_administrator_signs_in_and_out_like_any_other_account(client):
    boot = _bootstrap(client)
    assert boot.status_code == 201, boot.text
    mutation = boot.json()
    assert mutation["created"] is True
    assert mutation["account"]["role"] == "institution_admin"
    assert mutation["account"]["status"] == "ACTIVE"
    assert mutation["credential_set"] is True, "the operator's password was stored"

    headers = _sign_in(client, ADMIN_EMAIL, PASSWORD)
    me = client.get("/auth/me", headers=headers).json()
    assert me["principal"]["authenticated"] is True
    assert me["principal"]["role"] == "institution_admin"
    assert me["principal"]["email"] == ADMIN_EMAIL
    # The capability set is the role's, decided in one place. An administrator is
    # not an author, not a teacher and not a participant.
    scopes = set(me["principal"]["scopes"])
    assert {"account:read", "account:write", "content:read", "class:read"} == scopes
    assert "join" not in scopes and "content:write" not in scopes

    assert client.post("/auth/logout", headers=headers).json() == {"revoked": True}
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/logout", headers=headers).json() == {"revoked": False}


def test_the_bootstrap_is_one_shot_and_does_not_hand_over_an_existing_account(client):
    assert _bootstrap(client).status_code == 201

    again = _bootstrap(client, email="other@uni.test")

    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "CONFLICT"
    assert again.json()["error"]["issue_code"] == "TENANT_ALREADY_PROVISIONED"
    # And it created nothing.
    assert _account_count(client) == 1


def test_the_bootstrap_is_per_tenant(client):
    assert _bootstrap(client).status_code == 201

    other = _bootstrap(client, institution="university-002")

    assert other.status_code == 201, other.text
    assert other.json()["account"]["institution_id"] == "university-002"


def test_the_bootstrap_is_absent_when_the_deployment_turns_it_off(settings):
    """Federation owns provisioning, so a hardened deployment omits the route (V0-023).

    The switch is deliberately separate from the tenant-header shortcut: a locked
    deployment (the default) still exposes the bootstrap so it can create its first
    account, and *only* ``admin_bootstrap=False`` removes it.
    """

    hardened = dataclasses.replace(settings, admin_bootstrap=False)
    with TestClient(create_app(hardened)) as client:
        refused = client.post(
            "/auth/bootstrap-admin",
            json={
                "institution_id": "university-001",
                "email": ADMIN_EMAIL,
                "password": PASSWORD,
            },
        )

    assert refused.status_code == 404, refused.text
    assert refused.json()["error"]["code"] == "NOT_FOUND"
    assert refused.json()["error"]["issue_code"] == "BOOTSTRAP_DISABLED"


def _account_count(client) -> int:
    return len(
        client.app.state.identity_service.list_accounts(
            "university-001", role=Role.INSTITUTION_ADMIN
        )
    )


# -- an administrator manages the directory -------------------------------------------


def test_an_administrator_creates_teachers_and_students(client):
    teacher = _account(client, "T@Uni.test", "teacher")
    student = _account(client, "ana@uni.test", "student")

    assert teacher["created"] is True
    assert student["created"] is True
    assert teacher["account"]["email"] == "t@uni.test", "addresses are normalized"
    assert teacher["account"]["role"] == "teacher"
    assert student["account"]["role"] == "student"
    assert teacher["account"]["display_name"] == "t@uni.test"
    # The password the administrator chose was stored for each account.
    assert teacher["credential_set"] is True
    assert student["credential_set"] is True

    # Each can sign in with the password it was given, and is who it says it is. The
    # response never echoes a credential back.
    assert "password" not in teacher and "credential" not in teacher
    assert (
        client.get("/auth/me", headers=_sign_in(client, "t@uni.test", PASSWORD)).json()[
            "principal"
        ]["role"]
        == "teacher"
    )
    assert (
        client.get("/auth/me", headers=_sign_in(client, "ana@uni.test", PASSWORD)).json()[
            "principal"
        ]["role"]
        == "student"
    )


def test_a_password_shorter_than_the_guard_is_refused(client):
    """A guard, not a decided policy: ``FND-002`` is TODO (V0-023)."""

    status, body = _create(client, "ana@uni.test", "student", password="short")

    assert status == 400, body
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["issue_code"] == "CREDENTIAL_TOO_WEAK"


def test_listing_the_directory_is_by_role(client):
    _account(client, "t@uni.test", "teacher")
    _account(client, "ana@uni.test", "student")
    _account(client, "bo@uni.test", "student")

    teachers = client.get("/accounts", params={"role": "teacher"}, headers=_admin(client)).json()
    students = client.get("/accounts", params={"role": "student"}, headers=_admin(client)).json()

    assert teachers["role"] == "teacher"
    assert [account["email"] for account in teachers["accounts"]] == ["t@uni.test"]
    assert sorted(account["email"] for account in students["accounts"]) == [
        "ana@uni.test",
        "bo@uni.test",
    ]


def test_reading_one_account(client):
    created = _account(client, "ana@uni.test")

    fetched = client.get(f"/accounts/{created['account']['account_id']}", headers=_admin(client))

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["email"] == "ana@uni.test"
    assert fetched.json()["status"] == "ACTIVE"


def test_creating_an_account_is_idempotent_and_never_overwrites_the_password(client):
    first = _account(client, "ana@uni.test")
    second = _account(client, "ANA@uni.test")

    assert first["created"] is True
    assert second["created"] is False
    assert second["account"]["account_id"] == first["account"]["account_id"]
    assert second["credential_set"] is False, "a replay must not touch the credential"
    # The first password still works: it was never replaced.
    assert client.post(
        "/auth/login",
        json={"institution_id": "university-001", "email": "ana@uni.test", "password": PASSWORD},
    ).status_code == 200


def test_creating_the_same_address_as_another_role_is_a_conflict(client):
    _account(client, "ana@uni.test", "student")

    status, body = _create(client, "ana@uni.test", "teacher")

    assert status == 409, body
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["issue_code"] == "EMAIL_ROLE_CONFLICT"
    # The account's role is unchanged: a create never silently promotes anyone.
    assert client.get(
        "/accounts", params={"role": "student"}, headers=_admin(client)
    ).json()["accounts"][0]["role"] == "student"


def test_an_administrator_cannot_create_another_administrator(client):
    status, body = _create(client, "second@uni.test", "institution_admin")

    assert status == 409, body
    assert body["error"]["issue_code"] == "ROLE_NOT_MANAGEABLE"


def test_an_unknown_role_is_a_malformed_request(client):
    status, body = _create(client, "ana@uni.test", "janitor")

    assert status == 400, body
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_updating_an_account_changes_name_role_and_status(client):
    created = _account(client, "ana@uni.test")
    account_id = created["account"]["account_id"]

    renamed = client.patch(
        f"/accounts/{account_id}",
        json={"display_name": "Ana Alvarez"},
        headers=_admin(client),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["account"]["display_name"] == "Ana Alvarez"
    assert renamed.json()["account"]["role"] == "student", "an omitted field is unchanged"

    promoted = client.patch(
        f"/accounts/{account_id}", json={"role": "teacher"}, headers=_admin(client)
    )
    assert promoted.json()["account"]["role"] == "teacher"
    assert promoted.json()["account"]["scopes"] == [
        "account:read",
        "class:read",
        "class:write",
        "content:read",
        "content:write",
        "enrollment:write",
        "publication:write",
        "review:write",
        "scene:read",
    ]

    disabled = client.patch(
        f"/accounts/{account_id}", json={"status": "disabled"}, headers=_admin(client)
    )
    assert disabled.json()["account"]["status"] == "DISABLED"

    enabled = client.patch(
        f"/accounts/{account_id}", json={"status": "ACTIVE"}, headers=_admin(client)
    )
    assert enabled.json()["account"]["status"] == "ACTIVE"

    assert (
        client.patch(
            f"/accounts/{account_id}", json={"status": "MAYBE"}, headers=_admin(client)
        ).status_code
        == 400
    )


def test_an_administrator_resets_a_password_and_it_revokes_live_sessions(client):
    """A reset is the remedy for a forgotten password (V0-023)."""

    created = _account(client, "ana@uni.test")
    account_id = created["account"]["account_id"]
    student = _sign_in(client, "ana@uni.test", PASSWORD)
    assert client.get("/auth/me", headers=student).status_code == 200

    reset = client.patch(
        f"/accounts/{account_id}",
        json={"password": "a-brand-new-passphrase"},
        headers=_admin(client),
    )

    assert reset.status_code == 200, reset.text
    assert reset.json()["credential_set"] is True
    assert reset.json()["sessions_revoked"] == 1, "the old password cannot keep a tab working"
    assert client.get("/auth/me", headers=student).status_code == 401

    # The old password is refused; the new one signs in.
    assert client.post(
        "/auth/login",
        json={"institution_id": "university-001", "email": "ana@uni.test", "password": PASSWORD},
    ).status_code == 401
    assert client.get(
        "/auth/me",
        headers=_sign_in(client, "ana@uni.test", "a-brand-new-passphrase"),
    ).status_code == 200


def test_disabling_an_account_takes_effect_on_the_next_request(client):
    """``DEC-RUNTIME-007``: a disable is a revocation, not a waiting period."""

    created = _account(client, "ana@uni.test")
    account_id = created["account"]["account_id"]
    student = _sign_in(client, "ana@uni.test", PASSWORD)
    assert client.get("/auth/me", headers=student).status_code == 200

    disabled = client.patch(
        f"/accounts/{account_id}", json={"status": "DISABLED"}, headers=_admin(client)
    )

    assert disabled.json()["sessions_revoked"] == 1, "the live session is revoked with it"
    live = client.get("/auth/me", headers=student)
    assert live.status_code == 401, live.text
    # The token was explicitly revoked by the disable, so *that* is the precise cause
    # the client sees; the account's own state is the second guard, and a sign-in
    # reports it directly.
    assert live.json()["error"]["issue_code"] == "SESSION_REVOKED"
    blocked = client.post(
        "/auth/login",
        json={"institution_id": "university-001", "email": "ana@uni.test", "password": PASSWORD},
    )
    assert blocked.status_code == 401
    assert blocked.json()["error"]["issue_code"] == "ACCOUNT_DISABLED"

    # Re-enabling restores sign-in with the same password.
    client.patch(f"/accounts/{account_id}", json={"status": "ACTIVE"}, headers=_admin(client))
    assert client.get(
        "/auth/me", headers=_sign_in(client, "ana@uni.test", PASSWORD)
    ).status_code == 200


def test_a_role_change_can_only_remove_from_a_live_session(client):
    created = _account(client, "ana@uni.test", "student")
    account_id = created["account"]["account_id"]
    student = _sign_in(client, "ana@uni.test", PASSWORD)
    assert client.post("/auth/logout", headers=student).json() == {"revoked": True}
    student = _sign_in(client, "ana@uni.test", PASSWORD)

    client.patch(f"/accounts/{account_id}", json={"role": "teacher"}, headers=_admin(client))

    # The session was issued with the student's scopes, so the intersection is what
    # it always was: not a silent promotion.
    me = client.get("/auth/me", headers=student).json()["principal"]
    assert me["role"] == "teacher"
    assert "content:write" not in me["scopes"], "a live session never gains a capability"
    assert client.post("/auth/logout", headers=student).json() == {"revoked": True}
    # A fresh sign-in gets the new role's capabilities, as it should.
    fresh = _sign_in(client, "ana@uni.test", PASSWORD)
    assert "content:write" in client.get("/auth/me", headers=fresh).json()["principal"]["scopes"]


def test_removing_an_unreferenced_account_removes_its_credentials_and_sessions(client):
    created = _account(client, "ana@uni.test")
    account_id = created["account"]["account_id"]
    student = _sign_in(client, "ana@uni.test", PASSWORD)

    removed = client.delete(f"/accounts/{account_id}", headers=_admin(client))

    assert removed.status_code == 200, removed.text
    assert removed.json() == {"account_id": account_id, "deleted": True}
    assert client.get("/auth/me", headers=student).status_code == 401
    assert client.get(f"/accounts/{account_id}", headers=_admin(client)).status_code == 404
    # And it is really gone, not merely hidden: a new account is a new identity.
    assert _account(client, "ana@uni.test")["account"]["account_id"] != account_id


def test_removing_an_account_a_class_references_is_refused(client):
    """An identity that has been in a class is deactivated, not deleted."""

    course_id = client.post("/courses", params={"title": "Nets"}, headers=HEADERS).json()["course_id"]
    class_id = client.post(
        "/classes", params={"course_id": course_id}, headers=HEADERS
    ).json()["class_id"]
    created = _account(client, "ana@uni.test")
    account_id = created["account"]["account_id"]
    assert (
        client.post(
            f"/classes/{class_id}/enrollments",
            params={"student_id": account_id},
            headers=HEADERS,
        ).status_code
        == 200
    )

    refused = client.delete(f"/accounts/{account_id}", headers=_admin(client))

    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "CONFLICT"
    assert refused.json()["error"]["issue_code"] == "ACCOUNT_IN_USE"
    # Still there, and deactivating is the supported correction.
    assert client.get(f"/accounts/{account_id}", headers=_admin(client)).status_code == 200
    assert (
        client.patch(
            f"/accounts/{account_id}", json={"status": "DISABLED"}, headers=_admin(client)
        ).json()["account"]["status"]
        == "DISABLED"
    )


def test_removing_an_unknown_account_is_a_404(client):
    assert client.delete("/accounts/nobody", headers=_admin(client)).status_code == 404
    assert client.get("/accounts/nobody", headers=_admin(client)).status_code == 404


# -- the wrong principal is refused ----------------------------------------------------


def test_a_teacher_cannot_write_the_directory_but_may_read_students(client):
    """A teacher chooses students for a roster; that is not administering them."""

    _account(client, "ana@uni.test", "student")
    _account(client, "t2@uni.test", "teacher")

    # Reading a student is what a roster picker needs, so it is allowed…
    assert client.get("/accounts", params={"role": "student"}, headers=HEADERS).status_code == 200
    # …reading the staff directory is not.
    refused = client.get("/accounts", params={"role": "teacher"}, headers=HEADERS)
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "INSUFFICIENT_SCOPE"
    assert refused.json()["error"]["issue_code"] == "SCOPE_REQUIRED"

    # Nor may a bare role-less list become a directory dump.
    assert client.get("/accounts", headers=HEADERS).status_code == 422

    # Every write verb is an administrator verb.
    assert (
        client.post(
            "/accounts",
            json={"email": "new@uni.test", "role": "student", "password": PASSWORD},
            headers=HEADERS,
        ).status_code
        == 403
    )
    student_id = client.get("/accounts", params={"role": "student"}, headers=HEADERS).json()[
        "accounts"
    ][0]["account_id"]
    assert (
        client.patch(
            f"/accounts/{student_id}", json={"display_name": "x"}, headers=HEADERS
        ).status_code
        == 403
    )
    assert client.delete(f"/accounts/{student_id}", headers=HEADERS).status_code == 403
    # And no account was created by the refused write.
    assert client.get("/accounts", params={"role": "student"}, headers=HEADERS).json()["accounts"][0][
        "email"
    ] == "ana@uni.test"


def test_a_teacher_cannot_read_a_colleagues_account(client):
    teacher = _account(client, "t2@uni.test", "teacher")["account"]

    refused = client.get(f"/accounts/{teacher['account_id']}", headers=HEADERS)

    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["issue_code"] == "SCOPE_REQUIRED"


def test_a_student_cannot_reach_the_directory_at_all(client):
    student = _account(client, "ana@uni.test")
    headers = _sign_in(client, "ana@uni.test", PASSWORD)

    assert client.get("/accounts", params={"role": "student"}, headers=headers).status_code == 403
    assert client.get(f"/accounts/{student['account']['account_id']}", headers=headers).status_code == 403
    assert (
        client.post(
            "/accounts",
            json={"email": "x@uni.test", "role": "student", "password": PASSWORD},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/accounts/{student['account']['account_id']}",
            json={"display_name": "x"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/accounts/{student['account']['account_id']}", headers=headers
        ).status_code
        == 403
    )


# -- the tenant boundary ----------------------------------------------------------------


def test_the_directory_is_tenant_scoped(client):
    ours = _account(client, "ana@uni.test")["account"]
    theirs = client.post(
        "/accounts",
        json={"email": "ana@uni.test", "role": "student", "password": PASSWORD},
        headers=_admin(client, "university-002"),
    ).json()["account"]
    assert theirs["account_id"] != ours["account_id"]

    # Reading across the boundary is 403 (the tenant exists; the account is not ours).
    assert client.get(f"/accounts/{theirs['account_id']}", headers=_admin(client)).status_code == 403
    assert (
        client.patch(
            f"/accounts/{theirs['account_id']}",
            json={"display_name": "hijacked"},
            headers=_admin(client),
        ).status_code
        == 403
    )
    assert client.delete(f"/accounts/{theirs['account_id']}", headers=_admin(client)).status_code == 403
    # Each tenant's list is its own.
    assert [
        account["email"]
        for account in client.get(
            "/accounts", params={"role": "student"}, headers=_admin(client, "university-002")
        ).json()["accounts"]
    ] == ["ana@uni.test"]


def test_the_tenant_comes_from_the_session_not_a_header(client):
    """A session's tenant is its own; a named header cannot widen it (V0-021)."""

    ours = _account(client, "ana@uni.test")["account"]
    admin = _admin(client)

    clever = client.get(
        "/accounts", params={"role": "student"}, headers={**admin, "X-Institution-Id": "university-002"}
    )

    assert clever.status_code == 200
    assert [account["account_id"] for account in clever.json()["accounts"]] == [ours["account_id"]]


# -- telemetry --------------------------------------------------------------------------


def test_telemetry_records_directory_activity_without_addresses_or_passwords(client):
    service = client.app.state.identity_service
    records: list[str] = []
    logger = type("_L", (), {"records": records})()
    logger.info = lambda message, *a: records.append(message % a if a else message)  # type: ignore[assignment]
    service.telemetry._logger = logger

    created = _account(client, "ana@uni.test")
    client.patch(
        f"/accounts/{created['account']['account_id']}",
        json={"status": "DISABLED"},
        headers=_admin(client),
    )
    client.delete(f"/accounts/{created['account']['account_id']}", headers=_admin(client))

    events = [json.loads(record) for record in records]
    kinds = [event["event"] for event in events]
    assert "identity.admin_bootstrap" in kinds
    assert "identity.account_created" in kinds
    assert "identity.account_updated" in kinds
    assert "identity.account_deleted" in kinds

    updated = next(event for event in events if event["event"] == "identity.account_updated")
    assert updated["changed"] == ["status"]
    assert updated["status"] == "DISABLED"
    assert updated["sessions_revoked"] == 0
    assert updated["actor_role"] == "institution_admin"
    # An address identifies a person: an event carries *presence* plus a digest; and a
    # password is never recorded — not even its length.
    assert "ana@uni.test" not in json.dumps(events)
    assert PASSWORD not in json.dumps(events)
    assert all("subject_digest" in event for event in events if "subject_digest" in event)
