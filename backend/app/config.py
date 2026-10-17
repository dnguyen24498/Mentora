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

    @classmethod
    def from_env(cls, base_dir: Path | str | None = None) -> "Settings":
        base = Path(base_dir or os.environ.get("MENTORA_DATA_DIR", "var"))
        return cls(
            database_path=Path(os.environ.get("MENTORA_DB_PATH", base / "mentora.db")),
            object_root=Path(os.environ.get("MENTORA_OBJECT_ROOT", base / "objects")),
            frontend_dist=Path(os.environ.get("MENTORA_FRONTEND_DIST", _default_frontend_dist())),
            home_region=os.environ.get("MENTORA_HOME_REGION", DEFAULT_HOME_REGION),
        )
