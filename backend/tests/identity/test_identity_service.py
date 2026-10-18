"""Login, sessions, roles and invitations (V0-021).

The properties that matter here are the security ones, so they are asserted
directly rather than inferred from a happy path:

* the tenant comes from the **session**, never from the request;
* only a token **digest** is stored;
* an expired or revoked session cannot authorize;
* capabilities cannot exceed the account's *current* role;
* an invitation is create-or-link, and never changes an existing account's role.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.common.errors import ValidationError
from app.identity.errors import (
    ISSUE_ACCOUNT_DISABLED,
    ISSUE_EMAIL_ROLE_CONFLICT,
    ISSUE_SESSION_EXPIRED,
    ISSUE_SESSION_REQUIRED,
    ISSUE_SESSION_REVOKED,
    ISSUE_SESSION_UNKNOWN,
    InvitationConflictError,
    SessionError,
)
from app.identity.models import Role, Scope, hash_token
from app.identity.repository import IdentityRepository, normalize_email
from app.identity.service import IdentityService
from app.identity.testing import ScriptedAuthenticator, ScriptedOutcome

TENANT = "uni-1"
OTHER_TENANT = "uni-2"

#: The student capability set, in the stable order a session stores it (by scope
#: value), so the assertions below cannot drift from the implementation silently.
STUDENT_SCOPES = (Scope.CLASS_READ, Scope.JOIN, Scope.SCENE_READ)


def build(conn: sqlite3.Connection, **kwargs) -> tuple[IdentityService, IdentityRepository]:
    repository = IdentityRepository(conn)
    authenticator = kwargs.pop("authenticator", None) or ScriptedAuthenticator(
        script=[ScriptedOutcome(accept=True)]
    )
    service = IdentityService(
        repository,
        authenticator,
        session_ttl_seconds=kwargs.pop("session_ttl_seconds", 3600),
        **kwargs,
    )
    return service, repository


def seed_student(repository: IdentityRepository, email="ana@uni.test", tenant=TENANT):
    return repository.create_account(
        institution_id=tenant, email=email, display_name="Ana", role=Role.STUDENT
    )


# -- login ---------------------------------------------------------------------------
def test_login_mints_a_session_and_stores_only_the_digest(conn):
    service, repository = build(conn)
    account = seed_student(repository)

    result = service.login(TENANT, "ana@uni.test", "whatever")

    assert result.authenticated
    raw = result.issuance.raw_token
    assert raw and result.issuance.principal.account_id == account.account_id
    # The digest is what is stored, and the raw token appears in no column.
    rows = conn.execute("SELECT * FROM auth_sessions").fetchall()
    assert len(rows) == 1
    stored = dict(rows[0])
    assert stored["token_sha256"] == hash_token(raw)
    assert raw not in set(str(value) for value in stored.values())


def test_login_denies_when_the_capability_refuses(conn):
    service, repository = build(
        conn, authenticator=ScriptedAuthenticator(script=[ScriptedOutcome(accept=False)])
    )
    seed_student(repository)

    result = service.login(TENANT, "ana@uni.test", "wrong")

    assert not result.authenticated
    assert result.error_code == "INVALID_CREDENTIALS"
    assert conn.execute("SELECT COUNT(*) AS total FROM auth_sessions").fetchone()["total"] == 0


def test_login_does_not_raise_when_the_capability_is_unavailable(conn):
    service, _ = build(conn)

    class Exploding(ScriptedAuthenticator):
        def _verify_credential(self, request, account_id):  # type: ignore[override]
            raise RuntimeError("down")

    service = IdentityService(IdentityRepository(conn), Exploding())

    result = service.login(TENANT, "ana@uni.test", "x")

    assert not result.authenticated
    assert result.error_code == "AUTHENTICATION_UNAVAILABLE"


def test_a_disabled_account_cannot_log_in(conn):
    service, repository = build(conn)
    account = seed_student(repository)
    conn.execute(
        "UPDATE accounts SET disabled_at = ? WHERE account_id = ?",
        (datetime.now(timezone.utc).isoformat(), account.account_id),
    )

    result = service.login(TENANT, "ana@uni.test", "x")

    assert not result.authenticated
    assert result.error_code == ISSUE_ACCOUNT_DISABLED


# -- session verification ------------------------------------------------------------
def test_a_session_resolves_to_a_principal_with_the_tenant_from_the_session(conn):
    service, repository = build(conn)
    seed_student(repository)
    raw = service.login(TENANT, "ana@uni.test", "x").issuance.raw_token

    principal = service.principal_for_token(raw)

    assert principal.authenticated
    assert principal.institution_id == TENANT
    assert principal.role is Role.STUDENT
    assert principal.scopes == STUDENT_SCOPES
    # The student capability set is exactly "attend the class": nothing that writes.
    assert not principal.has(Scope.PUBLICATION_WRITE)
    assert not principal.has(Scope.ENROLLMENT_WRITE)


def test_scope_values_are_stored_in_a_stable_order(conn):
    """Determinism matters: the same role must always produce the same session row."""

    service, repository = build(
        conn,
        authenticator=ScriptedAuthenticator(
            script=[ScriptedOutcome(accept=True), ScriptedOutcome(accept=True)]
        ),
    )
    account = repository.create_account(
        institution_id=TENANT, email="t@uni.test", display_name="T", role=Role.TEACHER
    )
    raws = [service.login(TENANT, "t@uni.test", "x").issuance.raw_token for _ in range(2)]

    scopes = [service.principal_for_token(raw).scopes for raw in raws]

    assert scopes[0] == scopes[1]
    assert list(scopes[0]) == sorted(scopes[0], key=lambda scope: scope.value)
    assert account.role is Role.TEACHER


@pytest.mark.parametrize(
    "raw,issue_code",
    [
        (None, ISSUE_SESSION_REQUIRED),
        ("", ISSUE_SESSION_REQUIRED),
        ("not-a-token", ISSUE_SESSION_UNKNOWN),
    ],
)
def test_an_unusable_session_is_refused_with_a_named_cause(conn, raw, issue_code):
    service, _ = build(conn)

    with pytest.raises(SessionError) as raised:
        service.principal_for_token(raw)

    assert raised.value.issue_code == issue_code


def test_a_revoked_session_cannot_authorize(conn):
    service, repository = build(conn)
    seed_student(repository)
    raw = service.login(TENANT, "ana@uni.test", "x").issuance.raw_token

    assert service.sign_out(raw) is True
    with pytest.raises(SessionError) as raised:
        service.principal_for_token(raw)

    assert raised.value.issue_code == ISSUE_SESSION_REVOKED


def test_sign_out_is_idempotent(conn):
    """A retried sign-out is not an error (DEC-RUNTIME-003)."""

    service, repository = build(conn)
    seed_student(repository)
    raw = service.login(TENANT, "ana@uni.test", "x").issuance.raw_token

    assert service.sign_out(raw) is True
    assert service.sign_out(raw) is False
    assert service.sign_out("never-issued") is False


def test_an_expired_session_cannot_authorize(conn):
    """The deadline is enforced on read, not only at issue (short-lived tokens)."""

    now = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
    service, repository = build(conn, session_ttl_seconds=60, clock=lambda: now)
    seed_student(repository)
    raw = service.login(TENANT, "ana@uni.test", "x").issuance.raw_token

    later = IdentityService(
        IdentityRepository(conn),
        ScriptedAuthenticator(script=[ScriptedOutcome(accept=True)]),
        session_ttl_seconds=60,
        clock=lambda: now + timedelta(seconds=61),
    )

    with pytest.raises(SessionError) as raised:
        later.principal_for_token(raw)

    assert raised.value.issue_code == ISSUE_SESSION_EXPIRED


def test_capabilities_cannot_outlive_the_role(conn):
    """A narrowed role takes effect on the next request, not at session expiry."""

    service, repository = build(conn)
    account = repository.create_account(
        institution_id=TENANT, email="t@uni.test", display_name="T", role=Role.TEACHER
    )
    raw = service.login(TENANT, "t@uni.test", "x").issuance.raw_token
    assert service.principal_for_token(raw).has(Scope.PUBLICATION_WRITE)

    conn.execute("UPDATE accounts SET role = ? WHERE account_id = ?", ("student", account.account_id))

    principal = service.principal_for_token(raw)
    assert not principal.has(Scope.PUBLICATION_WRITE)
    # The session's own capabilities are intersected with the role it holds *now*,
    # and an intersection can only ever remove: a role change never grants a session
    # a capability it was not issued with. (Widening a role — or a role whose scope
    # set is not a superset, as teacher's no longer is — therefore takes effect on
    # the account's next sign-in, not retroactively.)
    assert set(principal.scopes) == {Scope.CLASS_READ, Scope.SCENE_READ}
    assert not principal.has(Scope.JOIN)


def test_a_principal_never_carries_another_tenants_identity(conn):
    """The tenant is a property of the session: naming another one changes nothing."""

    service, repository = build(conn)
    seed_student(repository, tenant=OTHER_TENANT, email="bo@uni.test")
    raw = service.login(OTHER_TENANT, "bo@uni.test", "x").issuance.raw_token

    principal = service.principal_for_token(raw)

    assert principal.institution_id == OTHER_TENANT


def test_the_development_shortcut_is_marked_unauthenticated(conn):
    """The pre-auth shortcut must be distinguishable from a signed-in user."""

    service, _ = build(conn)

    principal = service.development_principal(TENANT)

    assert principal.authenticated is False
    assert principal.account_id is None
    assert principal.session_id is None
    # It still carries the teacher capability set, because the V0 flows need it,
    # but nothing downstream can mistake it for a session.
    assert principal.has(Scope.PUBLICATION_WRITE)


# -- invitations ---------------------------------------------------------------------
def test_inviting_is_create_or_link(conn):
    service, _ = build(conn)

    first = service.invite_student(TENANT, "Ana@Uni.test", "Ana")
    second = service.invite_student(TENANT, "ana@uni.test")

    assert first.created is True
    assert second.created is False
    assert first.account.account_id == second.account.account_id
    assert first.account.email == normalize_email("Ana@Uni.test") == "ana@uni.test"
    # One account, and the second invitation issues no new credential.
    assert conn.execute("SELECT COUNT(*) AS total FROM accounts").fetchone()["total"] == 1
    assert second.development_credential is None


def test_an_invitation_never_changes_an_existing_role(conn):
    service, repository = build(conn)
    repository.create_account(
        institution_id=TENANT, email="t@uni.test", display_name="T", role=Role.TEACHER
    )

    with pytest.raises(InvitationConflictError) as raised:
        service.invite_student(TENANT, "t@uni.test")

    assert raised.value.issue_code == ISSUE_EMAIL_ROLE_CONFLICT
    assert repository.find_account_by_email(TENANT, "t@uni.test").role is Role.TEACHER


@pytest.mark.parametrize("email", ["", "   ", "not-an-email", "ana@uni test"])
def test_an_invalid_invitation_is_refused(conn, email):
    service, _ = build(conn)

    with pytest.raises(ValidationError):
        service.invite_student(TENANT, email)


def test_the_same_email_in_another_tenant_is_another_account(conn):
    """Institution isolation: one address, two institutions, two accounts."""

    service, _ = build(conn)

    here = service.invite_student(TENANT, "ana@uni.test")
    there = service.invite_student(OTHER_TENANT, "ana@uni.test")

    assert here.account.account_id != there.account.account_id


def test_the_authenticator_identity_is_reported_for_traceability(conn):
    """Which capability issued a session must be visible, including that it is a mock."""

    service, _ = build(conn)

    identity = service.authenticator_identity

    assert identity["kind"] == "TEST_DOUBLE"
    assert identity["id"] == "scripted@1.0.0"
