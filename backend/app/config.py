"""Runtime configuration.

Environment-specific values stay outside the code (``docs/ARC_OVERVIEW.md``
section 33). For local/dev/tests this uses SQLite and a local object store
directory; production swaps in the PostgreSQL-equivalent store and real object
storage behind the same repositories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MiB streaming size limit
DEFAULT_MAX_ARCHIVE_ENTRIES = 5_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # zip-bomb guard

#: The home region a class runs in (``DEC-DEPLOY-002``: "each class has a home
#: region"). ``DEC-TECH-009`` (primary cloud/provider/regions) is ``OPEN``, so this
#: is *configuration*, never a decided geography: the default names the local
#: single-host deployment rather than asserting a cloud region.
DEFAULT_HOME_REGION = "local-1"

#: Lifetime of an authenticated session token (V0-021). ``docs/security/
#: IDENTITY_AUTHORIZATION_AND_TOKENS.md`` requires **short-lived** least-privilege
#: tokens; the concrete number is configuration, not architecture. Eight hours
#: covers a teaching day without a session outliving it.
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60


def _default_frontend_dist() -> Path:
    # backend/app/config.py -> repo root/frontend/dist
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


@dataclass(frozen=True)
class Settings:
    database_path: Path
    object_root: Path
    frontend_dist: Path = field(default_factory=_default_frontend_dist)
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_archive_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES
    #: The home region a session pins (``DEC-DEPLOY-002``); see DEFAULT_HOME_REGION.
    home_region: str = DEFAULT_HOME_REGION
    #: Whether the **pre-auth development shortcut** is accepted: a request with no
    #: session is trusted for whatever ``X-Institution-Id`` it names. V0-021 makes
    #: the tenant come from an authenticated principal; this shortcut exists so the
    #: V0 flows (and their tests) keep working before an institutional-federation
    #: deployment, and it is *not* authentication — a request that uses it is
    #: reported as ``authenticated: false``. Set ``MENTORA_DEV_TENANT_HEADER=0`` to
    #: require a session on every route.
    dev_tenant_header: bool = True
    #: How long an issued session token stays valid (short-lived, least privilege).
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS

    @classmethod
    def from_env(cls, base_dir: Path | str | None = None) -> "Settings":
        base = Path(base_dir or os.environ.get("MENTORA_DATA_DIR", "var"))
        shortcut = os.environ.get("MENTORA_DEV_TENANT_HEADER", "1").strip().lower()
        return cls(
            database_path=Path(os.environ.get("MENTORA_DB_PATH", base / "mentora.db")),
            object_root=Path(os.environ.get("MENTORA_OBJECT_ROOT", base / "objects")),
            frontend_dist=Path(os.environ.get("MENTORA_FRONTEND_DIST", _default_frontend_dist())),
            home_region=os.environ.get("MENTORA_HOME_REGION", DEFAULT_HOME_REGION),
            dev_tenant_header=shortcut not in {"0", "false", "no", "off"},
            session_ttl_seconds=int(
                os.environ.get("MENTORA_SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS)
            ),
        )
