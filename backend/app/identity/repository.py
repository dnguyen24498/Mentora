"""Tenant-scoped persistence for accounts and sessions (V0-021).

Every read and write is scoped by ``institution_id``, in one place
(``docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md``). ``get_account``
follows the convention V0-009 established for classes: fetch by id alone so the two
refusals stay distinct — an account that does not exist is ``404``, one that belongs
to another institution is ``403``, and never a silent ``None`` a caller could read
as absence.

Only the **digest** of a session token is stored, exactly as a join credential is
(``DEC-RUNTIME-007``): a read of this table cannot yield a usable token. Credential
material is *not* here at all — it belongs to the authenticator
(:class:`~app.identity.port.CredentialStore`), so no domain module can see it.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from app.common.errors import NotFoundError, TenantAccessError
from app.db.database import transaction
from app.identity.models import Account, AuthSession, Role, Scope


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def normalize_email(email: str) -> str:
    """One canonical subject form, so ``Ana@School`` and ``ana@school`` are one
    account. Used for lookup and for the uniqueness constraint."""

    return (email or "").strip().lower()


class IdentityRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- accounts --------------------------------------------------------------------
    def create_account(
        self,
        *,
        institution_id: str,
        email: str,
        display_name: str,
        role: Role,
        account_id: Optional[str] = None,
    ) -> Account:
        """Create an account. The ``(institution, email)`` uniqueness is the DB's."""

        new_id = account_id or _new_id()
        subject = normalize_email(email)
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO accounts "
                "(account_id, institution_id, email, display_name, role, created_at, disabled_at) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (new_id, institution_id, subject, display_name.strip() or subject, role.value, _now()),
            )
        return self.get_account(institution_id, new_id)

    def get_account(self, institution_id: str, account_id: str) -> Account:
        """One account, or a classified failure (``404`` vs ``403``, as V0-009)."""

        row = self._conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"account {account_id!r} not found")
        if row["institution_id"] != institution_id:
            raise TenantAccessError("account belongs to another institution")
        return Account.from_row(row)

    def find_account(self, institution_id: str, account_id: str) -> Optional[Account]:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE account_id = ? AND institution_id = ?",
            (account_id, institution_id),
        ).fetchone()
        return Account.from_row(row) if row is not None else None

    def find_account_by_email(self, institution_id: str, email: str) -> Optional[Account]:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE institution_id = ? AND email = ?",
            (institution_id, normalize_email(email)),
        ).fetchone()
        return Account.from_row(row) if row is not None else None

    def resolve_subject(self, institution_id: str, subject: str) -> Optional[str]:
        """``(tenant, subject) -> account_id``, for the authenticator's resolver.

        An unknown subject resolves to ``None`` rather than raising: the
        authenticator must do the same work either way, so the *return value* is not
        an enumeration oracle (``app.identity.port.Authenticator``).
        """

        row = self._conn.execute(
            "SELECT account_id FROM accounts WHERE institution_id = ? AND email = ?",
            (institution_id, normalize_email(subject)),
        ).fetchone()
        return row["account_id"] if row is not None else None

    def list_accounts(
        self, institution_id: str, *, role: Optional[Role] = None
    ) -> list[Account]:
        if role is None:
            rows = self._conn.execute(
                "SELECT * FROM accounts WHERE institution_id = ? "
                "ORDER BY display_name, email LIMIT 500",
                (institution_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM accounts WHERE institution_id = ? AND role = ? "
                "ORDER BY display_name, email LIMIT 500",
                (institution_id, role.value),
            ).fetchall()
        return [Account.from_row(row) for row in rows]

    # -- sessions --------------------------------------------------------------------
    def create_session(
        self,
        *,
        institution_id: str,
        account_id: str,
        token_sha256: str,
        scopes: Sequence[Scope],
        issued_at: str,
        expires_at: str,
    ) -> AuthSession:
        session_id = _new_id()
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO auth_sessions "
                "(session_id, institution_id, account_id, token_sha256, scopes, "
                " issued_at, expires_at, revoked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    session_id,
                    institution_id,
                    account_id,
                    token_sha256,
                    ",".join(scope.value for scope in scopes),
                    issued_at,
                    expires_at,
                ),
            )
        session = self.find_session(token_sha256)
        if session is None:  # pragma: no cover - the insert above just committed
            raise NotFoundError("session was not persisted")
        return session

    def find_session(self, token_sha256: str) -> Optional[AuthSession]:
        """Look a session up by digest alone.

        Deliberately *not* tenant-scoped by the caller: the tenant is a property of
        the session, not of the request, so a caller cannot address another tenant's
        session by naming it and the tenant follows from the token that is presented.
        """

        row = self._conn.execute(
            "SELECT * FROM auth_sessions WHERE token_sha256 = ?", (token_sha256,)
        ).fetchone()
        return AuthSession.from_row(row) if row is not None else None

    def revoke_session(self, token_sha256: str) -> bool:
        """Revoke a session. Idempotent: returns whether this call flipped it."""

        with transaction(self._conn):
            cur = self._conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? "
                "WHERE token_sha256 = ? AND revoked_at IS NULL",
                (_now(), token_sha256),
            )
            return cur.rowcount == 1

    def revoke_sessions_for_account(self, institution_id: str, account_id: str) -> int:
        """Revoke every live session of one account (sign-out everywhere)."""

        with transaction(self._conn):
            cur = self._conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? "
                "WHERE institution_id = ? AND account_id = ? AND revoked_at IS NULL",
                (_now(), institution_id, account_id),
            )
            return int(cur.rowcount or 0)

    def count_live_sessions(self, institution_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM auth_sessions "
            "WHERE institution_id = ? AND revoked_at IS NULL",
            (institution_id,),
        ).fetchone()
        return int(row["total"]) if row is not None else 0


__all__ = ["IdentityRepository", "normalize_email"]
