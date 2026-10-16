"""Read a stored Baseline Content Package back out of object storage (V0-006).

The inverse of :meth:`~app.compiler.package_builder.models.BaselinePackage.write_to`.
It exists so a read-only consumer (teacher review / publication) can serve a
package that was already built, instead of re-rendering the document: rendering
is the expensive part of the pipeline, and a preview must not pay for it again.

``manifest.json`` is the entry point — its presence is what makes a package
visible — and every listed file is read through the manifest, never by guessing a
path from the outside world (``DEC-CONTENT-004``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from app.common.errors import StorageError
from app.compiler.package_builder.layout import MANIFEST_FILENAME
from app.compiler.package_builder.models import BaselinePackage, PackageFile
from app.storage.object_store import ObjectStore


@dataclass(frozen=True)
class LoadedPackage:
    """A package read back from storage, plus its storage prefix."""

    prefix: str
    package: BaselinePackage

    @property
    def manifest(self) -> dict:
        return self.package.manifest

    def file(self, path: str) -> Optional[PackageFile]:
        return self.package.file(path)

    def data(self, path: str) -> bytes:
        """Bytes of a listed file; raises for a path the manifest does not list."""

        package_file = self.package.file(path)
        if package_file is None:
            raise StorageError(f"package does not list {path!r}")
        return package_file.data

    def data_json(self, path: str) -> dict:
        """A listed JSON document, parsed."""

        try:
            return json.loads(self.data(path).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageError(f"package document {path!r} is unreadable: {exc}") from exc

    def scene_paths(self) -> tuple[str, ...]:
        """Scene documents in manifest order (which is path order, i.e. lesson order)."""

        return tuple(
            path
            for path in self.package.paths()
            if path.startswith("scenes/") and path.endswith(".json")
        )

    def scene_for_order(self, order: int) -> Optional[dict]:
        """The scene document whose file name encodes ``order``."""

        prefix = f"scenes/{order:03d}-"
        for path in self.scene_paths():
            if path.startswith(prefix):
                return json.loads(self.data(path).decode("utf-8"))
        return None

    def lesson_plan(self) -> Optional[dict]:
        for path in self.package.paths():
            if path == "lesson-plan.json":
                return json.loads(self.data(path).decode("utf-8"))
        return None


def read_package(store: ObjectStore, prefix: str) -> Optional[LoadedPackage]:
    """Load the package at ``prefix``, or ``None`` when it was never built.

    A package whose manifest is absent is treated as absent: the manifest is
    written last, so an interrupted build is never half-visible. A manifest that
    exists but lists a missing file is a real integrity error and raises.
    """

    manifest_key = f"{prefix}/{MANIFEST_FILENAME}"
    if not store.exists(manifest_key):
        return None
    try:
        manifest = json.loads(store.get(manifest_key).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageError(f"package manifest at {manifest_key!r} is unreadable: {exc}") from exc

    files: list[PackageFile] = []
    for entry in manifest.get("files") or []:
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise StorageError(f"package manifest at {manifest_key!r} has a file without a path")
        data = store.get(f"{prefix}/{path}")
        files.append(PackageFile(path=path, media_type=entry.get("media_type", ""), data=data))
    return LoadedPackage(
        prefix=prefix, package=BaselinePackage(manifest=manifest, files=tuple(files))
    )


__all__ = ["LoadedPackage", "read_package"]
