"""Immutable object storage for source artifacts.

Object storage owns immutable binaries and is never the source of *state*
(``docs/architecture/16_DATA_STORAGE_AND_EVENTS.md``). The local implementation
writes atomically (temp file + ``os.replace``) under a content-addressed key so
an interrupted write never leaves a corrupt visible artifact (V0-002).
"""

from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from app.common.errors import StorageError


class ObjectStore(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes) -> str:
        """Persist bytes under ``key`` and return the stored key."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the bytes stored at ``key``."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether ``key`` exists."""


class LocalObjectStore(ObjectStore):
    """Filesystem object store rooted at ``root``.

    Keys are content-addressed and namespaced by tenant/course, so they are
    immutable: re-uploading identical bytes targets the same key.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        # Reject traversal before touching the filesystem.
        normalized = key.replace("\\", "/").lstrip("/")
        if ".." in normalized.split("/"):
            raise StorageError(f"invalid object key {key!r}")
        return self._root / normalized

    def put(self, key: str, data: bytes) -> str:
        path = self._path_for(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except OSError as exc:  # disk full, permission, transient storage error
            raise StorageError(f"failed to store object {key!r}: {exc}") from exc
        return key

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"object {key!r} not found") from exc

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()
