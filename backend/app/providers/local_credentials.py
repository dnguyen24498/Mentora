"""The local **development** credential adapter (V0-021).

**This is a mock, and everything about it says so.**

``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`` — *"Users authenticate through
institutional federation"* — and ``docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md``
— *"OIDC/OAuth users, workload identity services, short-lived least-privilege
tokens"* — together name the model, but **no ADR accepts a mechanism**, so this
module is the explicitly-approved *temporary* stand-in, the same shape ``ADR-P007``
gives the TTS mock while ``DEC-TECH-007`` is ``OPEN``. It must never be described as
the platform's authentication, and :attr:`LocalCredentialAuthenticator.identity`
reports ``kind="DEVELOPMENT_MOCK"`` in code so a session can always be traced back
to it.

What it does implement properly, because these are contract requirements rather
than adapter choices:

* only a **digest** is stored, with a per-account random salt, so a database read
  yields no credential (the same rule ``DEC-RUNTIME-007`` applies to join tokens);
* comparison is constant-time (``hmac.compare_digest``);
* an **unknown account costs the same as a wrong credential** — the dummy
  verification below — so login is not an enumeration oracle;
* a transient failure is classified as retryable and never leaks a vendor type.

It is dependency-free (stdlib ``hashlib.scrypt``) deliberately: no credential
library is chosen while the mechanism is undecided.

V0-023 makes the credential it manages a **password**: an administrator supplies an
initial one when creating an account (and can reset it), and an account holder can
change their own. This is still the mock standing in for federation — a password
here is a development convenience, not a decided mechanism, and no password
*policy* beyond a minimum-length guard is fixed (V0-022 left policy out of scope).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.db.database import transaction
from app.identity.port import (
    AuthenticationConfig,
    AuthenticationRequest,
    Authenticator,
    AuthenticatorIdentity,
    CredentialRecord,
    CredentialStore,
)

#: Names the KDF parameters in the stored record, so a future change is visible as
#: a different algorithm string rather than silently invalidating digests.
SCRYPT_ALGORITHM = "scrypt-n16384-r8-p1"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LENGTH = 32

#: A fixed salt for the dummy verification. Its only job is to make "no such
#: account" cost the same as "wrong credential".
_DUMMY_SALT = "0" * 32


def _derive(secret: str, salt: str) -> str:
    """scrypt digest of a credential, hex-encoded (stdlib only, no dependency)."""

    digest = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LENGTH,
    )
    return digest.hex()


class LocalCredentialStore(CredentialStore):
    """The adapter's own credential table.

    Kept here rather than in the domain repository on purpose: how a credential is
    represented is the *authenticator's* business, so no domain module can read one.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, institution_id: str, account_id: str) -> Optional[CredentialRecord]:
        row = self._conn.execute(
            "SELECT algorithm, salt, digest FROM account_credentials "
            "WHERE account_id = ? AND institution_id = ?",
            (account_id, institution_id),
        ).fetchone()
        if row is None:
            return None
        return CredentialRecord(
            algorithm=row["algorithm"], salt=row["salt"], digest=row["digest"]
        )

    def put(self, institution_id: str, account_id: str, record: CredentialRecord) -> None:
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO account_credentials "
                "(account_id, institution_id, algorithm, salt, digest, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(account_id) DO UPDATE SET "
                "algorithm = excluded.algorithm, salt = excluded.salt, "
                "digest = excluded.digest, updated_at = excluded.updated_at",
                (
                    account_id,
                    institution_id,
                    record.algorithm,
                    record.salt,
                    record.digest,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    #: Convenience for seeding a known credential (dev, tests, and the fixture
    #: dataset): stores the digest, never the secret.
    def set_credential(self, institution_id: str, account_id: str, secret: str) -> None:
        salt = secrets.token_hex(16)
        self.put(
            institution_id,
            account_id,
            CredentialRecord(
                algorithm=SCRYPT_ALGORITHM, salt=salt, digest=_derive(secret, salt)
            ),
        )


class LocalCredentialAuthenticator(Authenticator):
    """Verifies a locally stored credential. A development mock (see module docs)."""

    def __init__(
        self,
        store: CredentialStore,
        config: Optional[AuthenticationConfig] = None,
    ) -> None:
        super().__init__(config)
        self._store = store

    @property
    def identity(self) -> AuthenticatorIdentity:
        return AuthenticatorIdentity(
            name="local-credentials", version="1.0.0", kind="DEVELOPMENT_MOCK"
        )

    def _verify_credential(
        self, request: AuthenticationRequest, account_id: Optional[str]
    ) -> bool:
        if account_id is None:
            # No such subject: do the same work against a throwaway salt so the
            # refusal is indistinguishable from a wrong credential by timing.
            _derive(request.credential, _DUMMY_SALT)
            return False

        record = self._store.get(request.institution_id, account_id)
        if record is None:
            _derive(request.credential, _DUMMY_SALT)
            return False

        candidate = _derive(request.credential, record.salt)
        # Constant-time: a byte-by-byte compare leaks the digest prefix.
        return hmac.compare_digest(candidate, record.digest)

    def provision_credential(self, institution_id: str, account_id: str, secret: str) -> bool:
        """Store a **caller-supplied** password for an account (V0-023).

        This adapter manages local credentials, so it returns ``True``; a federation
        adapter returns ``False``, because the identity provider owns the credential.
        Only the digest is stored — the caller (an administrator setting an initial
        password, or an account holder changing their own) supplies the secret.
        """

        self.set_credential(institution_id, account_id, secret)
        return True

    def set_credential(self, institution_id: str, account_id: str, secret: str) -> None:
        """Set a known credential (seeding and tests)."""

        setter = getattr(self._store, "set_credential", None)
        if setter is None:  # pragma: no cover - a store that cannot seed
            salt = secrets.token_hex(16)
            self._store.put(
                institution_id,
                account_id,
                CredentialRecord(
                    algorithm=SCRYPT_ALGORITHM, salt=salt, digest=_derive(secret, salt)
                ),
            )
            return
        setter(institution_id, account_id, secret)


def build_local_authenticator(
    conn: sqlite3.Connection,
    *,
    config: Optional[AuthenticationConfig] = None,
) -> LocalCredentialAuthenticator:
    """The development wiring: local credentials in the relational store."""

    return LocalCredentialAuthenticator(LocalCredentialStore(conn), config)


__all__ = [
    "SCRYPT_ALGORITHM",
    "LocalCredentialAuthenticator",
    "LocalCredentialStore",
    "build_local_authenticator",
]
