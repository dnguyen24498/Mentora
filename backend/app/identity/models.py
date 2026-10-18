"""Accounts, roles, principals and sessions (V0-021).

``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md``: *"Users authenticate through
institutional federation; services use workload identity. Roles: platform/institution
admin, IT operator, course admin, teacher, moderator, student, auditor. Every request
validates tenant/course/class/resource. Normal student media permission is
subscribe-only."*

Two different things live in that paragraph, and this module only implements the
first:

* the **authorization** model is fixed and is what V0-021 adds — a principal is an
  account in exactly one institution, it carries a role, its capabilities are a
  least-privilege scope set derived from that role, and every request is validated
  against the tenant and the resource it names.
* the **authentication mechanism** is institutional federation, and *no accepted ADR
  decides a mechanism*. So nothing here decides one: :mod:`app.identity.port` is the
  seam, and :mod:`app.providers.local_credentials` is a development mock, labelled as
  one everywhere it appears (the same shape ``ADR-P007`` gives the TTS mock, where
  ``DEC-TECH-007`` is ``OPEN``).

The canonical role list names seven roles. V0 has a product surface for two of them,
so :class:`Role` names two — inventing the other five would be creating a decision
the specification has not made.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Role(str, Enum):
    """A principal's role. Only the roles V0 has a surface for are named."""

    TEACHER = "teacher"
    STUDENT = "student"


class Scope(str, Enum):
    """A capability a session may carry (least privilege, not a role string).

    Guards are written against these, so "a student cannot publish" is enforced by
    the *absence of a scope* rather than by a comparison someone can forget to add.
    """

    #: Schedule a class, start it, and move a running session.
    CLASS_WRITE = "class:write"
    #: Read a class, its session, its pinned tuple and its snapshot.
    CLASS_READ = "class:read"
    #: Create courses, upload material, compile renders.
    CONTENT_WRITE = "content:write"
    #: Read courses, decks, the built package and its renders.
    CONTENT_READ = "content:read"
    #: Record a review decision and draft lesson-order revisions.
    REVIEW_WRITE = "review:write"
    #: Seal and publish a course version.
    PUBLICATION_WRITE = "publication:write"
    #: Maintain a class roster.
    ENROLLMENT_WRITE = "enrollment:write"
    #: Read the scene a running session is presenting.
    SCENE_READ = "scene:read"
    #: Request a join credential for a running class.
    JOIN = "join"


#: Role -> capabilities. One place decides what a role may do, so a role can never
#: accumulate a capability by an endpoint forgetting to check.
ROLE_SCOPES: dict[Role, frozenset[Scope]] = {
    Role.TEACHER: frozenset(
        {
            Scope.CLASS_WRITE,
            Scope.CLASS_READ,
            Scope.CONTENT_WRITE,
            Scope.CONTENT_READ,
            Scope.REVIEW_WRITE,
            Scope.PUBLICATION_WRITE,
            Scope.ENROLLMENT_WRITE,
            Scope.SCENE_READ,
            Scope.JOIN,
        }
    ),
    # The student's set is exactly "attend the class": read the class and its
    # snapshot, read the scene being presented, ask to join. Nothing that writes.
    Role.STUDENT: frozenset({Scope.CLASS_READ, Scope.SCENE_READ, Scope.JOIN}),
}


def scopes_for(role: Role) -> tuple[Scope, ...]:
    """The scope set of a role, in a stable order (deterministic storage)."""

    return tuple(sorted(ROLE_SCOPES.get(role, frozenset()), key=lambda scope: scope.value))


def hash_token(raw_token: str) -> str:
    """Digest a bearer/session token for storage.

    Only the digest is ever stored, exactly as a join credential is
    (``DEC-RUNTIME-007``): a database read cannot yield a usable token.
    """

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Account:
    """A person in one institution with one role."""

    account_id: str
    institution_id: str
    email: str
    display_name: str
    role: Role
    created_at: str
    disabled_at: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None

    @classmethod
    def from_row(cls, row: Any) -> "Account":
        return cls(
            account_id=row["account_id"],
            institution_id=row["institution_id"],
            email=row["email"],
            display_name=row["display_name"],
            role=Role(row["role"]),
            created_at=row["created_at"],
            disabled_at=row["disabled_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "institution_id": self.institution_id,
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role.value,
            "created_at": self.created_at,
            "disabled": not self.is_active,
        }


@dataclass(frozen=True)
class AuthSession:
    """A short-lived, least-privilege session for one account."""

    session_id: str
    institution_id: str
    account_id: str
    token_sha256: str
    scopes: tuple[Scope, ...]
    issued_at: str
    expires_at: str
    revoked_at: Optional[str] = None

    def has(self, scope: Scope) -> bool:
        return scope in self.scopes

    @classmethod
    def from_row(cls, row: Any) -> "AuthSession":
        return cls(
            session_id=row["session_id"],
            institution_id=row["institution_id"],
            account_id=row["account_id"],
            token_sha256=row["token_sha256"],
            scopes=tuple(Scope(value) for value in (row["scopes"] or "").split(",") if value),
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "institution_id": self.institution_id,
            "account_id": self.account_id,
            "scopes": [scope.value for scope in self.scopes],
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked_at is not None,
        }


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, as the API sees it.

    ``authenticated`` is ``False`` only for the pre-auth development shortcut
    (``Settings.dev_tenant_header``), where the tenant is taken from a header and
    there is no account behind it. That distinction is carried in the response of
    ``GET /auth/me`` rather than smoothed over, so a client can tell whether it is
    actually signed in.
    """

    institution_id: str
    role: Role
    scopes: tuple[Scope, ...]
    account_id: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    session_id: Optional[str] = None
    expires_at: Optional[str] = None
    authenticated: bool = True

    @property
    def is_teacher(self) -> bool:
        return self.role is Role.TEACHER

    def has(self, scope: Scope) -> bool:
        return scope in self.scopes

    def to_dict(self) -> dict[str, Any]:
        return {
            "institution_id": self.institution_id,
            "role": self.role.value,
            "scopes": [scope.value for scope in self.scopes],
            "account_id": self.account_id,
            "email": self.email,
            "display_name": self.display_name,
            "session_id": self.session_id,
            "expires_at": self.expires_at,
            "authenticated": self.authenticated,
        }


@dataclass(frozen=True)
class IssuedSession:
    """A newly minted session: the row plus the **only** view of the raw token."""

    session: AuthSession
    raw_token: str
    principal: Principal

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.raw_token,
            "token_type": "Bearer",
            "expires_at": self.session.expires_at,
            "principal": self.principal.to_dict(),
        }


@dataclass(frozen=True)
class InvitedAccount:
    """A newly created account plus its one-time development credential.

    The credential is returned **once**, at creation, and only its digest is
    stored. With institutional federation in place there is no such value: the
    identity provider owns the credential and this field would carry a federation
    subject instead. It is a mock's affordance, and the API response says so.
    """

    account: Account
    enrollment: Any = None
    development_credential: Optional[str] = None
    created: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
