"""The runtime catalog: policy, region and compatibility (V0-009).

``docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md``'s runtime tuple has
members the *publication* does not own — ``policy``, ``home region``, and the
capability set the session admitted through. Those are resolved here, once, at
start, and then pinned in the :class:`~app.classroom.models.RuntimeSessionPlan`.
Resolving them at start is what "no runtime ``latest`` lookup" means: a value is
chosen exactly once per session and thereafter read from the session's own plan.

The catalog is **replaceable infrastructure**, like the renderer or the index
builder: ``DEC-TECH-009`` (cloud/provider/regions) is ``OPEN``, and the policy
service that will own these versions does not exist in V0. The baseline therefore
supplies named constants rather than inventing a policy store:

* ``policy_version`` — the *name of the default policy set* this platform applies,
  which is the set of LOCKED runtime defaults: group student microphones are
  unpublished by default (``DEC-TURN-001``), at most one student holds the speaking
  floor (``DEC-TURN-004``), VAD and STT run only during a valid floor
  (``DEC-TURN-005``), floor authorization is fenced by actor epoch and
  expires/revokes (``DEC-TURN-008``), raw student audio retention is off by default
  (an architectural invariant, ``docs/architecture/02_ARCHITECTURAL_INVARIANTS.md``),
  and no assessment subsystem exists. Pinning it records that a session ran under
  exactly those defaults, so a later policy change cannot silently reinterpret a
  recorded session.
* ``region`` — the class's home region (``DEC-DEPLOY-002``). It is configuration
  (:attr:`~app.config.Settings.home_region`), never a decided geography, because
  ``DEC-TECH-009`` is ``OPEN``.
* ``supported_ctf_schema_versions`` — the package envelope versions this runtime
  can actually serve. A package outside the set is refused at start rather than
  half-rendered, which is the "reject incompatible package" requirement.

Capability identity is *observed*, not configured: :func:`capability_version`
turns the admitted renderer's identity (``DEC-CONTENT-006`` provenance) into the
``name@version`` string the session pins, so a later renderer upgrade cannot
retroactively change what a session warmed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

#: The default policy set's version. See the module docstring for what it names.
BASELINE_POLICY_VERSION = "runtime-policy@1"

#: ``contracts/ctf/manifest.schema.json``'s ``schema_version`` is a const today;
#: this is the set of envelope versions the runtime admits, expressed as values so
#: a second version is an addition here rather than a scattered comparison.
SUPPORTED_CTF_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0.0",)


@dataclass(frozen=True)
class RuntimeDefaults:
    """The runtime-side members of the tuple, resolved from the catalog."""

    policy_version: str
    region: str
    supported_ctf_schema_versions: tuple[str, ...]


class RuntimeCatalog(ABC):
    """Replaceable source of the runtime-side tuple members."""

    @abstractmethod
    def defaults(self) -> RuntimeDefaults:
        """The policy/region/compatibility view to pin for a session starting now."""


class BaselineRuntimeCatalog(RuntimeCatalog):
    """The local baseline: named constants plus the configured home region."""

    def __init__(
        self,
        *,
        region: str,
        policy_version: str = BASELINE_POLICY_VERSION,
        supported_ctf_schema_versions: tuple[str, ...] = SUPPORTED_CTF_SCHEMA_VERSIONS,
    ) -> None:
        self._defaults = RuntimeDefaults(
            policy_version=policy_version,
            region=region,
            supported_ctf_schema_versions=tuple(supported_ctf_schema_versions),
        )

    def defaults(self) -> RuntimeDefaults:
        return self._defaults


def capability_version(identity: Mapping[str, Any]) -> str:
    """The pinned capability identity: ``name@version`` of the warmed renderer."""

    name = str(identity.get("name") or "unknown")
    version = str(identity.get("version") or "0")
    return f"{name}@{version}"


__all__ = [
    "BASELINE_POLICY_VERSION",
    "SUPPORTED_CTF_SCHEMA_VERSIONS",
    "BaselineRuntimeCatalog",
    "RuntimeCatalog",
    "RuntimeDefaults",
    "capability_version",
]
