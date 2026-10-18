"""Serve the slide a session is presenting, from the package that session pinned.

``DEC-CONTENT-005``: *"Published artifacts are immutable and active sessions pin all
compatible versions."* A student's learning page must therefore never ask "what is
the latest render of this deck" — it asks for slide *n* of the **package the session
pinned**, so publishing a correction mid-lesson changes nothing the class sees.

The bytes are read **through the manifest** (``DEC-CONTENT-004``: the package
envelope is what is consumed, and a file is addressed by what the manifest lists,
never by a path guessed from the outside world). Two files are read per scene: the
scene document, and the fallback asset its ``fallback_asset`` names. Each is
re-verified against the ``sha256`` the manifest recorded for it, so a file swapped in
storage between the session's start and a student's read is **refused** rather than
presented. The whole-package ``content_digest`` seal is verified once at session
start (``ClassroomService.start_class``); this per-file check protects exactly the
bytes being served, on every read, at the cost of reading two files instead of the
whole package.

A manifest that is itself replaced wholesale is caught at the next session start
rather than on every read — the cost of the alternative is re-hashing the whole
package for each slide a student turns to, which is the wrong trade for a read on
the lesson's hot path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from app.classroom.errors import (
    ISSUE_SCENE_CHECKSUM_MISMATCH,
    ISSUE_SCENE_UNAVAILABLE,
    PinnedSceneError,
)
from app.common.errors import NotFoundError, StorageError
from app.compiler.package_builder.layout import MANIFEST_FILENAME, package_prefix
from app.storage.object_store import ObjectStore

#: A self-limiting bound on one served scene file: a slide render is far smaller
#: than this, so exceeding it means the stored object is not what it claims.
MAX_SCENE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class PinnedScene:
    """One scene of the pinned package, as the class is presenting it."""

    package_id: str
    order: int
    scene_id: Optional[str]
    svg: bytes
    media_type: str = "image/svg+xml"

    @property
    def byte_size(self) -> int:
        return len(self.svg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "order": self.order,
            "scene_id": self.scene_id,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
        }


@dataclass(frozen=True)
class PinnedSceneSummary:
    """One scene's document, without its asset bytes.

    A student page needs to know how many slides the pinned package has and what
    each one says, so it can offer navigation and gather the narration. That is a
    read of the scene documents only — the asset (the heavy part) is fetched for
    the one slide actually on screen.
    """

    order: int
    scene_id: str
    fidelity: Optional[str]
    notes: Optional[str]
    text: tuple[str, ...]
    warnings: tuple[str, ...]
    object_count: int
    step_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "scene_id": self.scene_id,
            "fidelity": self.fidelity,
            "notes": self.notes,
            "text": list(self.text),
            "warnings": list(self.warnings),
            "object_count": self.object_count,
            "step_count": self.step_count,
        }


class PinnedSceneSource:
    """Reads one scene's slide out of a package that a session already pinned."""

    def __init__(self, store: ObjectStore, *, max_scene_bytes: int = MAX_SCENE_BYTES) -> None:
        self._store = store
        self._max_scene_bytes = max(1, int(max_scene_bytes))

    def scene(self, package_id: str, order: int) -> PinnedScene:
        """The slide for ``order`` in ``package_id``'s package.

        Raises :class:`~app.classroom.errors.PinnedSceneError` when the pinned
        package is not stored or a served file disagrees with its recorded digest,
        and :class:`~app.common.errors.NotFoundError` when the package has no scene
        at that position.
        """

        prefix = package_prefix(package_id)
        manifest = self._manifest(prefix)
        listed = self._listed_files(manifest)

        scene_path = self._scene_path(listed, order)
        if scene_path is None:
            raise NotFoundError(
                f"the package this session pinned has no scene {order}"
            )
        scene_document = self._read_listed(prefix, listed, scene_path)
        scene = self._parse(scene_path, scene_document, issue_code=ISSUE_SCENE_CHECKSUM_MISMATCH)

        asset = scene.get("fallback_asset")
        if not isinstance(asset, str) or not asset.startswith("assets/"):
            raise PinnedSceneError(
                f"the pinned scene {order} names no packaged fallback asset",
                issue_code=ISSUE_SCENE_UNAVAILABLE,
            )
        svg = self._read_listed(prefix, listed, asset)

        scene_id = scene.get("scene_id")
        if not isinstance(scene_id, str) or not scene_id:
            # The file name encodes the id when the document does not; the id is
            # only ever used for correlation, never for addressing a path.
            scene_id = scene_path.rsplit("/", 1)[-1].split("-", 1)[-1].removesuffix(".json")

        return PinnedScene(
            package_id=package_id, order=order, scene_id=scene_id, svg=svg
        )

    def scenes(self, package_id: str) -> tuple[PinnedSceneSummary, ...]:
        """Every scene document of the pinned package, in slide order.

        Reads the scene documents only — never an asset — so a client can build a
        slide list and its text without paying for the renders it is not showing.
        """

        prefix = package_prefix(package_id)
        manifest = self._manifest(prefix)
        listed = self._listed_files(manifest)

        summaries: list[PinnedSceneSummary] = []
        for order, path in self._scene_paths(listed):
            document = self._parse(path, self._read_listed(prefix, listed, path))
            summaries.append(self._summarize(order, path, document))
        return tuple(summaries)

    # -- internals ---------------------------------------------------------------------
    def _parse(
        self, path: str, data: bytes, *, issue_code: str = ISSUE_SCENE_UNAVAILABLE
    ) -> dict[str, Any]:
        try:
            document = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PinnedSceneError(
                f"the pinned scene document {path!r} is unreadable: {exc}",
                issue_code=issue_code,
            ) from exc
        if not isinstance(document, dict):
            raise PinnedSceneError(
                f"the pinned scene document {path!r} is not a scene",
                issue_code=issue_code,
            )
        return document

    def _summarize(self, order: int, path: str, document: dict[str, Any]) -> PinnedSceneSummary:
        objects = [obj for obj in (document.get("objects") or []) if isinstance(obj, dict)]
        text: list[str] = []
        for obj in objects:
            for paragraph in obj.get("paragraphs") or []:
                if not isinstance(paragraph, dict):
                    continue
                value = str(paragraph.get("text", ""))
                # Blank runs are structure, not content: the same rule the teacher
                # review projection uses, so the two never disagree.
                if value.strip():
                    text.append(value)
        scene_id = document.get("scene_id")
        if not isinstance(scene_id, str) or not scene_id:
            scene_id = path.rsplit("/", 1)[-1].split("-", 1)[-1].removesuffix(".json")
        notes = document.get("notes")
        fidelity = document.get("fidelity")
        warnings = document.get("warnings") or []
        return PinnedSceneSummary(
            order=order,
            scene_id=scene_id,
            fidelity=fidelity if isinstance(fidelity, str) else None,
            notes=notes if isinstance(notes, str) and notes.strip() else None,
            text=tuple(text),
            warnings=tuple(str(warning) for warning in warnings),
            object_count=len(objects),
            step_count=len(document.get("steps") or []),
        )

    def _manifest(self, prefix: str) -> dict[str, Any]:
        key = f"{prefix}/{MANIFEST_FILENAME}"
        if not self._store.exists(key):
            raise PinnedSceneError(
                f"the package this session pinned ({prefix!r}) is not stored"
            )
        return self._parse(key, self._store.get(key), issue_code=ISSUE_SCENE_CHECKSUM_MISMATCH)

    def _listed_files(self, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """``path -> manifest entry``.

        This map *is* the reference list: a file is only ever read when the manifest
        names it, so a caller cannot turn a scene read into an arbitrary object read.
        """

        listed: dict[str, dict[str, Any]] = {}
        for entry in manifest.get("files") or []:
            path = entry.get("path") if isinstance(entry, dict) else None
            if isinstance(path, str) and path:
                listed[path] = entry
        return listed

    def _scene_paths(self, listed: dict[str, dict[str, Any]]) -> list[tuple[int, str]]:
        """``(order, path)`` for every scene document the manifest lists, in order."""

        found: list[tuple[int, str]] = []
        for path in sorted(listed):
            if not path.startswith("scenes/") or not path.endswith(".json"):
                continue
            stem = path[len("scenes/") : -len(".json")]
            head, _, _ = stem.partition("-")
            try:
                found.append((int(head), path))
            except ValueError:
                # Not a scene document (the manifest is the authority on paths, and
                # the layout contract names scenes ``scenes/<order>-<id>.json``).
                continue
        return sorted(found)

    def _scene_path(self, listed: dict[str, dict[str, Any]], order: int) -> Optional[str]:
        prefix = f"scenes/{order:03d}-"
        for path in sorted(listed):
            if path.startswith(prefix) and path.endswith(".json"):
                return path
        return None

    def _read_listed(
        self, prefix: str, listed: dict[str, dict[str, Any]], path: str
    ) -> bytes:
        entry = listed.get(path)
        if entry is None:
            raise PinnedSceneError(
                f"the pinned package does not list {path!r}",
                issue_code=ISSUE_SCENE_UNAVAILABLE,
            )
        try:
            data = self._store.get(f"{prefix}/{path}")
        except StorageError as exc:
            raise PinnedSceneError(
                f"the pinned file {path!r} is not readable: {exc}",
                issue_code=ISSUE_SCENE_UNAVAILABLE,
            ) from exc
        if len(data) > self._max_scene_bytes:
            raise PinnedSceneError(
                f"the pinned file {path!r} is larger than the "
                f"{self._max_scene_bytes} byte read limit"
            )
        expected = entry.get("sha256")
        if isinstance(expected, str) and expected:
            observed = hashlib.sha256(data).hexdigest()
            if observed != expected:
                # The file changed under a session that pinned it: refused, never
                # presented (DEC-CONTENT-005: a pinned version does not move).
                raise PinnedSceneError(
                    f"the pinned file {path!r} no longer matches the digest the "
                    "package recorded for it",
                    issue_code=ISSUE_SCENE_CHECKSUM_MISMATCH,
                )
        return data


__all__ = [
    "MAX_SCENE_BYTES",
    "PinnedScene",
    "PinnedSceneSource",
    "PinnedSceneSummary",
]
