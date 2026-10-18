"""Identity: accounts, roles, principals and sessions (V0-021).

The domain half of authentication and the whole of authorization. It depends on
nothing outside itself and the standard library plus the shared error vocabulary;
:mod:`app.providers` supplies the credential capability through
:class:`app.identity.port.Authenticator`, and a layering test enforces that
direction (``tests/identity/test_layering.py``), exactly as the speech domain does.
"""

from __future__ import annotations

from app.identity.models import (
    Account,
    AuthSession,
    InvitedAccount,
    IssuedSession,
    Principal,
    Role,
    Scope,
    hash_token,
    scopes_for,
)
from app.identity.repository import IdentityRepository, normalize_email
from app.identity.service import IdentityService, LoginResult

__all__ = [
    "Account",
    "AuthSession",
    "IdentityRepository",
    "IdentityService",
    "InvitedAccount",
    "IssuedSession",
    "LoginResult",
    "Principal",
    "Role",
    "Scope",
    "hash_token",
    "normalize_email",
    "scopes_for",
]
