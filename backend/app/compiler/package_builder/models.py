"""Package builder models (V0-006).

A package is a set of immutable files plus the manifest that lists them by
checksum. The manifest is *not* part of ``BaselinePackage.files`` — it is the
envelope and the commit point, and it is written last (so an interrupted build
leaves no discoverable package).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from app.compiler.package_builder.layout import MANIFEST_FILENAME, package_prefix

#: Step kind emitted by the baseline builder. ``contracts/ctf/scene.schema.json``
#: leaves ``steps`` unconstrained; the baseline renders every object visible in
#: reading order because V0-004 extracts no animation timing (see
#: ``contracts/ctf/PACKAGE_LAYOUT.md`` and the task's known limitations).
STEP_KIND_ALL_VISIBLE = "ALL_VISIBLE"


@dataclass(frozen=True)
class PackageMetadata:
    """Envelope identity. Injected so a build is reproducible in tests."""

    tenant_id: str
    course_id: str
    course_version: str
    content_package_version: str
    lesson_plan_version: str
    lesson_id: str
    package_id: str
    created_at: str
    knowledge_index_version: str
    teaching_graph_version: Optional[str] = None
    #: Compiler identity that produced the content (provenance, not a rebuild key).
    compiler_version: Optional[str] = None
    source_sha256: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "course_id": self.course_id,
            "course_version": self.course_version,
            "content_package_version": self.content_package_version,
            "lesson_plan_version": self.lesson_plan_version,
            "lesson_id": self.lesson_id,
            "package_id": self.package_id,
            "created_at": self.created_at,
            "knowledge_index_version": self.knowledge_index_version,
            "teaching_graph_version": self.teaching_graph_version,
            "compiler_version": self.compiler_version,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class PackageFile:
    """One immutable file inside a package."""

    path: str
    media_type: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def byte_size(self) -> int:
        return len(self.data)

    def to_manifest_entry(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256, "media_type": self.media_type}

    def json_text(self) -> str:
        return self.data.decode("utf-8")


@dataclass(frozen=True)
class SceneStep:
    """A discrete reveal step (``DEC-CONTENT-007``).

    ``safe_markers`` on the lesson plan reference ``step_id`` values, so these
    ids are an interface and must stay stable.
    """

    step_id: str
    order: int
    kind: str
    object_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "order": self.order,
            "kind": self.kind,
            "object_ids": list(self.object_ids),
        }


@dataclass(frozen=True)
class LessonSection:
    """One baseline lesson section (``contracts/ctf/lesson-plan.schema.json``)."""

    section_id: str
    type: str
    safe_markers: tuple[str, ...]
    scene_id: Optional[str] = None
    scene_step_id: Optional[str] = None
    script: Optional[str] = None
    fallback_script: Optional[str] = None
    concept_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "type": self.type,
            "concept_id": self.concept_id,
            "scene_id": self.scene_id,
            "scene_step_id": self.scene_step_id,
            "script": self.script,
            "safe_markers": list(self.safe_markers),
            "fallback_script": self.fallback_script,
        }


@dataclass(frozen=True)
class LessonPlan:
    """The baseline fallback lesson order, derived from scene order only."""

    lesson_plan_version: str
    lesson_id: str
    sections: tuple[LessonSection, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson_plan_version": self.lesson_plan_version,
            "lesson_id": self.lesson_id,
            "sections": [s.to_dict() for s in self.sections],
        }


@dataclass(frozen=True)
class BaselinePackage:
    """A built package: manifest + the files it references, in memory."""

    manifest: dict[str, Any]
    files: tuple[PackageFile, ...] = field(default_factory=tuple)

    @property
    def package_id(self) -> str:
        return str(self.manifest["package_id"])

    @property
    def manifest_bytes(self) -> bytes:
        """Canonical manifest bytes: sorted keys, stable separators."""

        return json.dumps(self.manifest, sort_keys=True, indent=2).encode("utf-8")

    @property
    def manifest_file(self) -> PackageFile:
        from app.compiler.package_builder.layout import MEDIA_TYPE_JSON

        return PackageFile(
            path=MANIFEST_FILENAME, media_type=MEDIA_TYPE_JSON, data=self.manifest_bytes
        )

    def file(self, path: str) -> Optional[PackageFile]:
        for candidate in self.files:
            if candidate.path == path:
                return candidate
        return None

    def paths(self) -> tuple[str, ...]:
        return tuple(f.path for f in self.files)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe view (no file bytes) for reports and API responses."""

        return {
            "manifest": self.manifest,
            "files": [f.to_manifest_entry() for f in self.files],
        }

    def write_to(self, store: Any, *, prefix: Optional[str] = None) -> str:
        """Persist the package under ``prefix``; the manifest is written last.

        Returns the prefix. Re-writing an identical package overwrites identical
        bytes (the operation is idempotent, like every other compiler stage).
        """

        base = prefix or package_prefix(self.package_id)
        for package_file in sorted(self.files, key=lambda f: f.path):
            store.put(f"{base}/{package_file.path}", package_file.data)
        # Commit point: a reader that does not see the manifest sees no package.
        manifest = self.manifest_file
        store.put(f"{base}/{manifest.path}", manifest.data)
        return base


__all__ = [
    "STEP_KIND_ALL_VISIBLE",
    "BaselinePackage",
    "LessonPlan",
    "LessonSection",
    "PackageFile",
    "PackageMetadata",
    "SceneStep",
]
