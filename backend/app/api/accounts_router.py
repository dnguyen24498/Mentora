"""The directory: create, read, update and remove accounts (V0-022).

Routes (``contracts/openapi/openapi.yaml``):

* ``POST   /accounts``          — create a teacher or a student (create-or-link).
* ``GET    /accounts``          — the tenant's accounts of one role.
* ``GET    /accounts/{id}``     — one account.
* ``PATCH  /accounts/{id}``     — display name, role, enabled state.
* ``DELETE /accounts/{id}``     — remove an account that no class references.

Three things are deliberate here:

* **Capabilities, not role names.** Every verb is guarded by ``account:read`` or
  ``account:write``, and the capability set is decided once, in
  :data:`app.identity.models.ROLE_SCOPES`. A route never learns a role string, so
  adding a role cannot silently grant it a verb.
* **The administrator cannot multiply itself.** :data:`MANAGEABLE_ROLES` holds the
  roles this surface creates and changes; ``institution_admin`` is deliberately not
  among them. Administrator accounts come from the deployment bootstrap
  (:meth:`app.identity.service.IdentityService.bootstrap_administrator`) or, in a
  federated deployment, from the identity provider.
* **The roster guard is composed here.** Whether an account may be *removed* is not
  the identity domain's fact — it is whether a class references it — so this module
  asks :class:`~app.classroom.service.ClassroomService` before deleting, and the
  identity domain stays unaware of classrooms. The guard is a policy check rather
  than a database invariant; a concurrent enrolment during a delete is not a
  scenario the V0 single-writer store expresses, and it is documented rather than
  implied.

The tenant always comes from the principal, never from the request, so an
administrator of one institution cannot read or write another's directory by naming
it.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends

from app.api.security import ApiSecurity
from app.classroom.service import ClassroomService
from app.common.errors import ValidationError
from app.identity.errors import (
    ISSUE_SCOPE_REQUIRED,
    AccountInUseError,
    RoleNotManageableError,
    ScopeDeniedError,
)
from app.identity.models import (
    MANAGEABLE_ROLES,
    TEACHER_LISTABLE_ROLES,
    Principal,
    Role,
    Scope,
)


def _role(value: str, *, allowed: frozenset[Role]) -> Role:
    """Parse a role name, refusing one this surface does not manage.

    An unknown name is a malformed request (``400``); a name that *exists* but is not
    managed here is a conflict with policy (``409``), and the two are kept apart so a
    client never has to guess which one it hit.
    """

    try:
        role = Role(value)
    except ValueError:
        raise ValidationError(
            f"{value!r} is not a role; expected one of "
            + ", ".join(sorted(item.value for item in Role))
        ) from None
    if role not in allowed:
        raise RoleNotManageableError(
            f"{role.value!r} is not a manageable role here; administrator accounts are "
            "provisioned by the deployment bootstrap (or, with federation, by the "
            "identity provider)"
        )
    return role


def build_accounts_router(
    security: ApiSecurity,
    classroom: ClassroomService,
) -> APIRouter:
    router = APIRouter()
    require = security.require

    @router.get("/accounts")
    def list_accounts(
        role: str,
        principal: Principal = Depends(require(Scope.ACCOUNT_READ)),
    ) -> dict[str, Any]:
        """The institution's accounts of one role.

        An explicit ``role`` is **required**, so this cannot drift into an accidental
        directory dump. A caller without ``account:write`` (a teacher) may list
        students only: choosing students for a roster is not the same as reading the
        staff directory.
        """

        requested = _role(role, allowed=frozenset({Role.TEACHER, Role.STUDENT}))
        if not principal.has(Scope.ACCOUNT_WRITE) and requested not in TEACHER_LISTABLE_ROLES:
            raise ScopeDeniedError(
                f"listing {requested.value} accounts is an administration capability",
                issue_code=ISSUE_SCOPE_REQUIRED,
                scope=Scope.ACCOUNT_WRITE.value,
            )

        accounts = security.identity.list_accounts(principal.institution_id, role=requested)
        return {
            "institution_id": principal.institution_id,
            "role": requested.value,
            "accounts": [account.to_dict() for account in accounts],
        }

    @router.post("/accounts", status_code=201)
    def create_account(
        email: str,
        role: str,
        principal: Principal = Depends(require(Scope.ACCOUNT_WRITE)),
        display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a teacher or a student. Returns a **one-time** credential, if any.

        Create-or-link: the same address and role returns the existing account with
        ``created: false`` and no credential, so a retry can never re-mint a secret
        (``DEC-RUNTIME-003``).
        """

        requested = _role(role, allowed=MANAGEABLE_ROLES)
        mutation = security.identity.create_account(
            principal.institution_id,
            email=email,
            role=requested,
            display_name=display_name or "",
            actor_role=principal.role.value,
        )
        return mutation.to_dict()

    @router.get("/accounts/{account_id}")
    def get_account(
        account_id: str,
        principal: Principal = Depends(require(Scope.ACCOUNT_READ)),
    ) -> dict[str, Any]:
        """One account of this institution (``404`` absent, ``403`` another tenant).

        The same rule as the list: a caller without ``account:write`` may read a
        **student** account (they choose students for rosters), but reading a
        colleague's account is an administration capability.
        """

        account = security.identity.account(principal.institution_id, account_id)
        if not principal.has(Scope.ACCOUNT_WRITE) and account.role not in TEACHER_LISTABLE_ROLES:
            raise ScopeDeniedError(
                f"reading a {account.role.value} account is an administration capability",
                issue_code=ISSUE_SCOPE_REQUIRED,
                scope=Scope.ACCOUNT_WRITE.value,
            )
        return account.to_dict()

    @router.patch("/accounts/{account_id}")
    def update_account(
        account_id: str,
        principal: Principal = Depends(require(Scope.ACCOUNT_WRITE)),
        display_name: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict[str, Any]:
        """Change an account's display name, role or enabled state.

        Disabling revokes the account's live sessions in the same call
        (``DEC-RUNTIME-007``); a role change is re-derived on the next read, so it can
        only ever *remove* a capability from a live session.
        """

        disabled: Optional[bool] = None
        if status is not None:
            normalized = status.strip().upper()
            if normalized not in {"ACTIVE", "DISABLED"}:
                raise ValidationError("status must be ACTIVE or DISABLED")
            disabled = normalized == "DISABLED"

        requested = None if role is None else _role(role, allowed=MANAGEABLE_ROLES)
        mutation = security.identity.update_account(
            principal.institution_id,
            account_id,
            display_name=display_name,
            role=requested,
            disabled=disabled,
            actor_role=principal.role.value,
        )
        return mutation.to_dict()

    @router.delete("/accounts/{account_id}")
    def delete_account(
        account_id: str,
        principal: Principal = Depends(require(Scope.ACCOUNT_WRITE)),
    ) -> dict[str, Any]:
        """Remove an account, unless a class references it.

        An identity that has been on a roster is **deactivated** instead
        (``PATCH status=DISABLED``), because a removal would orphan the roster and the
        audit trail behind it; that refusal is ``409 ACCOUNT_IN_USE``. Removing an
        account takes its credential material and sessions with it, atomically.
        """

        institution_id = principal.institution_id
        # Existence first, so "no such account" is a 404 rather than a 409 raised on
        # an id that is not this tenant's at all.
        security.identity.account(institution_id, account_id)
        if classroom.enrolled_anywhere(institution_id, account_id):
            raise AccountInUseError(
                "this account is on a class roster, so it is deactivated rather than "
                "removed; a removal would orphan the roster and its audit trail"
            )
        removed = security.identity.delete_account(
            institution_id, account_id, actor_role=principal.role.value
        )
        return {"account_id": account_id, "deleted": removed}

    return router


__all__ = ["build_accounts_router"]
