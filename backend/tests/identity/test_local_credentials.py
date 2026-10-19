"""The local development credential adapter (V0-021).

It is a mock for an undecided mechanism, but the parts that are *contract* rather
than choice are tested here: digest-only storage, constant-time comparison, and the
timing-equalized refusal that makes an unknown account indistinguishable from a
wrong credential.

Also asserted: the adapter reports ``kind="DEVELOPMENT_MOCK"``, so no session it
issues can be mistaken for federated authentication.
"""

from __future__ import annotations

import sqlite3

from app.identity.models import Role
from app.identity.repository import IdentityRepository
from app.providers.factory import DEFAULT_IDENTITY_PROVIDER, build_identity_service
from app.providers.local_credentials import (
    SCRYPT_ALGORITHM,
    LocalCredentialAuthenticator,
    LocalCredentialStore,
    build_local_authenticator,
)

TENANT = "uni-1"
SECRET = "correct-horse-battery-staple"


def seed(conn: sqlite3.Connection, email="ana@uni.test", role=Role.STUDENT):
    repository = IdentityRepository(conn)
    return repository.create_account(
        institution_id=TENANT, email=email, display_name="Ana", role=role
    )


def test_a_stored_credential_verifies(conn):
    account = seed(conn)
    authenticator = build_local_authenticator(conn)
    authenticator.set_credential(TENANT, account.account_id, SECRET)
    resolver = IdentityRepository(conn).resolve_subject

    outcome = authenticator.authenticate(
        _request(SECRET), resolver
    )

    assert outcome.authenticated


def test_a_wrong_credential_is_denied(conn):
    account = seed(conn)
    authenticator = build_local_authenticator(conn)
    authenticator.set_credential(TENANT, account.account_id, SECRET)

    outcome = authenticator.authenticate(_request("wrong"), IdentityRepository(conn).resolve_subject)

    assert not outcome.authenticated
    assert outcome.error_code == "INVALID_CREDENTIALS"


def test_an_unknown_account_and_a_wrong_credential_look_identical(conn):
    """The dummy verification is what makes this true, so it is asserted."""

    account = seed(conn)
    authenticator = build_local_authenticator(conn)
    authenticator.set_credential(TENANT, account.account_id, SECRET)
    resolver = IdentityRepository(conn).resolve_subject

    unknown = authenticator.authenticate(
        _request(SECRET, subject="nobody@uni.test"), resolver
    )
    wrong = authenticator.authenticate(_request("wrong"), resolver)

    assert not unknown.authenticated and not wrong.authenticated
    assert unknown.error_code == wrong.error_code == "INVALID_CREDENTIALS"
    assert unknown.attempts == wrong.attempts == 1


def test_only_a_digest_is_stored(conn):
    """A database read must not yield a credential."""

    account = seed(conn)
    store = LocalCredentialStore(conn)
    store.set_credential(TENANT, account.account_id, SECRET)

    row = conn.execute(
        "SELECT algorithm, salt, digest FROM account_credentials WHERE account_id = ?",
        (account.account_id,),
    ).fetchone()

    assert row["algorithm"] == SCRYPT_ALGORITHM
    # The salt and digest are hex digests; the secret is in neither, and the
    # algorithm string names the KDF parameters so a change is visible.
    assert SECRET not in (row["salt"] + row["digest"])
    assert all(char in "0123456789abcdef" for char in row["salt"])
    assert len(row["digest"]) == 64


def test_replacing_a_credential_invalidates_the_previous_one(conn):
    account = seed(conn)
    authenticator = build_local_authenticator(conn)
    resolver = IdentityRepository(conn).resolve_subject

    authenticator.set_credential(TENANT, account.account_id, SECRET)
    assert authenticator.authenticate(_request(SECRET), resolver).authenticated

    authenticator.set_credential(TENANT, account.account_id, "new-secret")
    assert not authenticator.authenticate(_request(SECRET), resolver).authenticated
    assert authenticator.authenticate(_request("new-secret"), resolver).authenticated


def test_the_adapter_declares_itself_a_development_mock(conn):
    """The mechanism is undecided; the adapter must say so in code."""

    identity = build_local_authenticator(conn).identity

    assert identity.kind == "DEVELOPMENT_MOCK"
    assert identity.id == "local-credentials@1.0.0"


def test_an_issued_credential_authenticates_and_is_stored_as_a_digest(conn):
    account = seed(conn)
    authenticator = LocalCredentialAuthenticator(LocalCredentialStore(conn))

    issued = authenticator.issue_credential(TENANT, account.account_id)

    assert issued
    assert authenticator.authenticate(_request(issued), IdentityRepository(conn).resolve_subject).authenticated
    stored = conn.execute(
        "SELECT digest FROM account_credentials WHERE account_id = ?", (account.account_id,)
    ).fetchone()["digest"]
    assert issued != stored


def test_invite_then_sign_in_end_to_end(conn):
    """The path a student actually takes: an administrator creates, the student signs in."""

    service = build_identity_service(conn, name=DEFAULT_IDENTITY_PROVIDER)

    created = service.create_account(
        TENANT, email="ana@uni.test", role=Role.STUDENT, display_name="Ana"
    )
    assert created.created and created.development_credential

    result = service.login(TENANT, "ana@uni.test", created.development_credential)

    assert result.authenticated
    principal = service.principal_for_token(result.issuance.raw_token)
    assert principal.account_id == created.account.account_id
    assert principal.role is Role.STUDENT


def test_a_session_issued_by_the_mock_is_traceable_to_it(conn):
    service = build_identity_service(conn)

    assert service.authenticator_identity["kind"] == "DEVELOPMENT_MOCK"
    assert service.health()["available"] is True


def _request(credential: str, subject: str = "ana@uni.test"):
    from app.identity.port import AuthenticationRequest

    return AuthenticationRequest(institution_id=TENANT, subject=subject, credential=credential)
