"""Baseline package validation (V0-006).

Validates a built :class:`~app.compiler.package_builder.models.BaselinePackage`
against ``contracts/ctf/{manifest,scene,lesson-plan}.schema.json`` and against
its own internal references.

Acceptance criteria implemented here:

* **Package validates against contracts** — required fields, enums, checksum
  shape, ``additionalProperties: false`` on the manifest, and the cross-document
  references the schemas cannot express (a scene's ``fallback_asset`` must be a
  file the manifest lists; a lesson section's ``scene_id``/``safe_markers`` must
  exist in the scenes).
* **Runtime package contains no source-parser dependency** — no source document
  (``.pptx``/``.ppt``/…) may appear among the package files, and every reference
  is package-relative (``DEC-CONTENT-001``).
* **Checksums detect mutation** — every manifest ``sha256`` is recomputed from
  the packaged bytes; any difference is ``CHECKSUM_MISMATCH``.

The checks are hand-rolled, exactly like ``validators/fidelity.py``: adding a
JSON-Schema library would be a new *production* dependency and no ADR accepts
one. Issue codes are plain strings (the established issue vocabulary), not
``ErrorCode`` members.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.common.errors import PublicationBlockedError
from app.compiler.models.ir import FIDELITY_REQUIRES_REVIEW, FIDELITY_VALUES
from app.compiler.package_builder.layout import (
    LESSON_PLAN_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_VERSION,
    SOURCE_DOCUMENT_EXTENSIONS,
)
from app.compiler.package_builder.models import BaselinePackage
from app.compiler.validators.fidelity import (
    SCENE_REQUIRED_FIELDS,
    SEVERITY_ERROR,
    SEVERITY_REVIEW,
    ValidationIssue,
    ValidationReport,
)

#: ``contracts/ctf/manifest.schema.json`` -> ``required`` / ``properties``.
MANIFEST_REQUIRED_FIELDS = (
    "schema_version",
    "package_id",
    "tenant_id",
    "course_id",
    "course_version",
    "content_package_version",
    "lesson_plan_versions",
    "knowledge_index_version",
    "files",
    "created_at",
)
MANIFEST_ALLOWED_FIELDS = frozenset(MANIFEST_REQUIRED_FIELDS) | {"teaching_graph_version"}
MANIFEST_FILE_REQUIRED_FIELDS = ("path", "sha256", "media_type")

#: ``contracts/ctf/lesson-plan.schema.json``.
LESSON_PLAN_REQUIRED_FIELDS = ("lesson_plan_version", "lesson_id", "sections")
LESSON_SECTION_REQUIRED_FIELDS = ("section_id", "type", "safe_markers")
LESSON_SECTION_TYPES = frozenset({"EXPLANATION", "EXAMPLE", "MEDIA", "QUIZ", "DISCUSSION"})

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class PackageValidationReport:
    """Outcome of validating one package against the CTF contracts."""

    ok: bool
    requires_review: bool
    package_id: str
    file_count: int
    scene_count: int
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == SEVERITY_ERROR)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "requires_review": self.requires_review,
            "package_id": self.package_id,
            "file_count": self.file_count,
            "scene_count": self.scene_count,
            "issues": [i.to_dict() for i in self.issues],
        }


def _issue(
    issues: list[ValidationIssue],
    code: str,
    message: str,
    *,
    severity: str = SEVERITY_ERROR,
    path: Optional[str] = None,
) -> None:
    issues.append(
        ValidationIssue(
            code=code,
            message=f"{path}: {message}" if path else message,
            severity=severity,
        )
    )


def _check_manifest_shape(manifest: dict[str, Any], issues: list[ValidationIssue]) -> None:
    for name in MANIFEST_REQUIRED_FIELDS:
        if name not in manifest:
            _issue(issues, "MISSING_MANIFEST_FIELD", f"required field {name!r} is absent")
    for name in manifest:
        if name not in MANIFEST_ALLOWED_FIELDS:
            # ``additionalProperties: false`` on the manifest schema.
            _issue(issues, "UNKNOWN_MANIFEST_FIELD", f"unexpected field {name!r}")

    version = manifest.get("schema_version")
    if version is not None and version != MANIFEST_SCHEMA_VERSION:
        _issue(
            issues,
            "INVALID_MANIFEST_SCHEMA_VERSION",
            f"schema_version {version!r} is not {MANIFEST_SCHEMA_VERSION!r}",
        )

    for name in ("package_id", "tenant_id", "course_id", "course_version",
                 "content_package_version", "created_at"):
        value = manifest.get(name)
        if value is not None and not isinstance(value, str):
            _issue(issues, "INVALID_MANIFEST_FIELD_TYPE", f"{name} must be a string")

    until = manifest.get("knowledge_index_version")
    if isinstance(until, str) and not until:
        _issue(issues, "MISSING_KNOWLEDGE_INDEX_VERSION", "knowledge_index_version is empty")

    plans = manifest.get("lesson_plan_versions")
    if not isinstance(plans, list) or not plans or not all(isinstance(p, str) for p in plans):
        _issue(
            issues,
            "INVALID_LESSON_PLAN_VERSIONS",
            "lesson_plan_versions must be a non-empty array of strings",
        )

    graph = manifest.get("teaching_graph_version")
    if graph is not None and not isinstance(graph, str):
        _issue(
            issues,
            "INVALID_TEACHING_GRAPH_VERSION",
            "teaching_graph_version must be a string or null",
        )
    # A null Teaching Graph version is valid: the baseline package is built
    # without AI enrichment (DEC-CONTENT-002).


def _check_file_entries(
    manifest: dict[str, Any],
    package: BaselinePackage,
    issues: list[ValidationIssue],
) -> None:
    entries = manifest.get("files")
    if not isinstance(entries, list):
        _issue(issues, "INVALID_FILES", "manifest files must be an array")
        return

    listed: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            _issue(issues, "INVALID_FILE_ENTRY", "each file entry must be an object")
            continue
        for name in MANIFEST_FILE_REQUIRED_FIELDS:
            if name not in entry:
                _issue(
                    issues,
                    "INVALID_FILE_ENTRY",
                    f"file entry is missing {name!r}",
                )
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            _issue(issues, "INVALID_FILE_ENTRY", "file entry path must be a non-empty string")
            continue
        if path == MANIFEST_FILENAME:
            _issue(
                issues,
                "MANIFEST_SELF_REFERENCE",
                "the manifest must not list itself (it is the commit point)",
                path=path,
            )
        if path in listed:
            _issue(issues, "DUPLICATE_FILE_PATH", "duplicate file path in manifest", path=path)
        listed.add(path)

        if any(path.lower().endswith(ext) for ext in SOURCE_DOCUMENT_EXTENSIONS):
            _issue(
                issues,
                "SOURCE_DOCUMENT_PRESENT",
                "the runtime package must not carry a source document (DEC-CONTENT-001)",
                path=path,
            )

        digest = entry.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.match(digest):
            _issue(
                issues,
                "INVALID_CHECKSUM_FORMAT",
                "sha256 must be 64 lowercase hex characters",
                path=path,
            )
            continue

        package_file = package.file(path)
        if package_file is None:
            _issue(
                issues,
                "MISSING_FILE_BYTES",
                "manifest lists a file that is not present in the package",
                path=path,
            )
            continue
        actual = hashlib.sha256(package_file.data).hexdigest()
        if actual != digest:
            _issue(
                issues,
                "CHECKSUM_MISMATCH",
                f"checksum mismatch: manifest {digest[:12]}… vs content {actual[:12]}…",
                path=path,
            )

    for package_file in package.files:
        if package_file.path not in listed:
            _issue(
                issues,
                "ORPHAN_FILE",
                "file is present in the package but not listed in the manifest",
                path=package_file.path,
            )


def _load_json(package: BaselinePackage, path: str, issues: list[ValidationIssue]) -> Any:
    package_file = package.file(path)
    if package_file is None:
        _issue(issues, "MISSING_DOCUMENT", "document is not present", path=path)
        return None
    try:
        return json.loads(package_file.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _issue(issues, "INVALID_JSON", f"document is not valid UTF-8 JSON: {exc}", path=path)
        return None


def _check_scenes(
    package: BaselinePackage, issues: list[ValidationIssue]
) -> tuple[set[str], dict[str, dict[str, Any]], int]:
    """Validate every ``scenes/*.json`` document; return ids, docs, and count."""

    scene_ids: set[str] = set()
    docs: dict[str, dict[str, Any]] = {}
    for package_file in package.files:
        if not package_file.path.startswith("scenes/") or not package_file.path.endswith(".json"):
            continue
        document = _load_json(package, package_file.path, issues)
        if not isinstance(document, dict):
            continue
        for name in SCENE_REQUIRED_FIELDS:
            if name not in document:
                _issue(issues, "MISSING_SCENE_FIELD", f"required field {name!r} is absent",
                       path=package_file.path)
        scene_id = document.get("scene_id")
        if not isinstance(scene_id, str) or not scene_id:
            _issue(issues, "INVALID_SCENE_ID", "scene_id must be a non-empty string",
                   path=package_file.path)
        elif scene_id in scene_ids:
            _issue(issues, "DUPLICATE_SCENE_ID", f"duplicate scene_id {scene_id!r}",
                   path=package_file.path)
        else:
            scene_ids.add(scene_id)
            docs[scene_id] = document

        fidelity = document.get("fidelity")
        if fidelity is not None and fidelity not in FIDELITY_VALUES:
            _issue(issues, "INVALID_FIDELITY",
                   f"fidelity {fidelity!r} is not one of {sorted(FIDELITY_VALUES)}",
                   path=package_file.path)

        dimensions = document.get("dimensions")
        if not isinstance(dimensions, dict) or not dimensions.get("width") \
                or not dimensions.get("height"):
            _issue(issues, "INVALID_SCENE_DIMENSIONS", "dimensions must be positive",
                   path=package_file.path)

        if not isinstance(document.get("steps"), list):
            _issue(issues, "INVALID_SCENE_STEPS", "steps must be an array",
                   path=package_file.path)

        objects = document.get("objects")
        if isinstance(objects, list):
            object_ids = {
                obj.get("source_id") for obj in objects if isinstance(obj, dict)
            }
            for step in document.get("steps") or []:
                if not isinstance(step, dict):
                    _issue(issues, "INVALID_SCENE_STEP", "each step must be an object",
                           path=package_file.path)
                    continue
                for name in ("step_id", "order", "kind"):
                    if name not in step:
                        _issue(issues, "INVALID_SCENE_STEP",
                               f"step is missing {name!r}", path=package_file.path)
                for object_id in step.get("object_ids") or []:
                    if object_id not in object_ids:
                        # Internal reference: a step may only reveal objects that
                        # exist in its own scene.
                        _issue(
                            issues,
                            "INVALID_REF",
                            f"step references unknown object {object_id!r}",
                            path=package_file.path,
                        )
    return scene_ids, docs, len(docs)


def _check_scene_assets(
    manifest: dict[str, Any], docs: dict[str, dict[str, Any]], issues: list[ValidationIssue]
) -> None:
    """Every scene's ``fallback_asset`` must be a file the manifest lists."""

    listed = {
        entry.get("path")
        for entry in (manifest.get("files") or [])
        if isinstance(entry, dict)
    }
    for scene_id, document in sorted(docs.items()):
        reference = document.get("fallback_asset")
        if not isinstance(reference, str) or not reference:
            _issue(issues, "MISSING_FALLBACK_ASSET",
                   f"scene {scene_id!r} has no fallback asset reference")
            continue
        if reference.startswith("renders/"):
            # The compiler's internal asset-store key leaked into the package.
            _issue(
                issues,
                "INVALID_REF",
                f"scene {scene_id!r} references the compiler asset store {reference!r}; "
                "package references must be package-relative",
            )
            continue
        if reference not in listed:
            _issue(
                issues,
                "MISSING_ASSET",
                f"scene {scene_id!r} references asset {reference!r} which the manifest "
                "does not list",
            )


def _check_lesson_plan(
    package: BaselinePackage,
    manifest: dict[str, Any],
    docs: dict[str, dict[str, Any]],
    issues: list[ValidationIssue],
) -> None:
    document = _load_json(package, LESSON_PLAN_FILENAME, issues)
    if not isinstance(document, dict):
        return
    for name in LESSON_PLAN_REQUIRED_FIELDS:
        if name not in document:
            _issue(issues, "MISSING_LESSON_PLAN_FIELD",
                   f"required field {name!r} is absent", path=LESSON_PLAN_FILENAME)

    plan_version = document.get("lesson_plan_version")
    if isinstance(plan_version, str):
        declared = manifest.get("lesson_plan_versions")
        if isinstance(declared, list) and plan_version not in declared:
            _issue(
                issues,
                "LESSON_PLAN_VERSION_MISMATCH",
                f"lesson plan version {plan_version!r} is not declared in the manifest",
                path=LESSON_PLAN_FILENAME,
            )

    sections = document.get("sections")
    if not isinstance(sections, list) or not sections:
        _issue(issues, "EMPTY_LESSON_PLAN", "the fallback lesson plan has no sections",
               path=LESSON_PLAN_FILENAME)
        return

    for section in sections:
        if not isinstance(section, dict):
            _issue(issues, "INVALID_LESSON_SECTION", "each section must be an object",
                   path=LESSON_PLAN_FILENAME)
            continue
        for name in LESSON_SECTION_REQUIRED_FIELDS:
            if name not in section:
                _issue(issues, "INVALID_LESSON_SECTION",
                       f"section is missing {name!r}", path=LESSON_PLAN_FILENAME)
        section_type = section.get("type")
        if section_type is not None and section_type not in LESSON_SECTION_TYPES:
            _issue(issues, "INVALID_SECTION_TYPE",
                   f"type {section_type!r} is not one of {sorted(LESSON_SECTION_TYPES)}",
                   path=LESSON_PLAN_FILENAME)
        markers = section.get("safe_markers")
        if not isinstance(markers, list) or not all(isinstance(m, str) for m in markers):
            _issue(issues, "INVALID_SAFE_MARKERS", "safe_markers must be an array of strings",
                   path=LESSON_PLAN_FILENAME)
            markers = []

        scene_id = section.get("scene_id")
        if scene_id is None:
            continue
        scene = docs.get(scene_id) if isinstance(scene_id, str) else None
        if scene is None:
            _issue(issues, "INVALID_REF",
                   f"section references unknown scene {scene_id!r}",
                   path=LESSON_PLAN_FILENAME)
            continue
        # The schema cannot express it: a safe marker must name a step of the
        # scene the section points at, or the runtime cannot pause safely.
        step_ids = {
            step.get("step_id")
            for step in (scene.get("steps") or [])
            if isinstance(step, dict)
        }
        for marker in markers:
            if marker not in step_ids:
                _issue(
                    issues,
                    "INVALID_REF",
                    f"section {section.get('section_id')!r} declares safe marker "
                    f"{marker!r} which is not a step of scene {scene_id!r}",
                    path=LESSON_PLAN_FILENAME,
                )
        entry_step = section.get("scene_step_id")
        if entry_step is not None and entry_step not in step_ids:
            _issue(
                issues,
                "INVALID_REF",
                f"section {section.get('section_id')!r} enters scene {scene_id!r} at "
                f"unknown step {entry_step!r}",
                path=LESSON_PLAN_FILENAME,
            )


def validate_package(
    package: BaselinePackage, *, render_validation: Optional[ValidationReport] = None
) -> PackageValidationReport:
    """Validate a built package against the CTF contracts and its own references.

    ``render_validation`` is the V0-005 fidelity gate for the document the
    package was built from. A document that failed the gate must not become a
    package (``FAILED`` renders block publication), so a non-publishable render
    report is an error here too.
    """

    issues: list[ValidationIssue] = []
    manifest = package.manifest if isinstance(package.manifest, dict) else {}
    if not isinstance(package.manifest, dict):
        _issue(issues, "INVALID_MANIFEST", "the manifest must be a JSON object")

    _check_manifest_shape(manifest, issues)
    _check_file_entries(manifest, package, issues)
    scene_ids, scene_docs, scene_count = _check_scenes(package, issues)
    _check_scene_assets(manifest, scene_docs, issues)
    _check_lesson_plan(package, manifest, scene_docs, issues)

    if not scene_ids:
        _issue(issues, "NO_SCENES", "the package contains no scenes")

    for scene_id, document in sorted(scene_docs.items()):
        if document.get("fidelity") in FIDELITY_REQUIRES_REVIEW:
            _issue(
                issues,
                "DEGRADED_REQUIRES_REVIEW",
                f"scene {scene_id!r} has fidelity {document.get('fidelity')}",
                severity=SEVERITY_REVIEW,
            )

    if render_validation is not None:
        if not render_validation.publishable:
            _issue(
                issues,
                "RENDER_NOT_PUBLISHABLE",
                "the render fidelity gate failed, so no package may be built",
            )
        if render_validation.requires_review:
            _issue(
                issues,
                "RENDER_REQUIRES_REVIEW",
                "the render gate flagged this document for human review",
                severity=SEVERITY_REVIEW,
            )

    errors = [i for i in issues if i.severity == SEVERITY_ERROR]
    review = [i for i in issues if i.severity == SEVERITY_REVIEW]
    return PackageValidationReport(
        ok=not errors,
        requires_review=bool(review),
        package_id=str(manifest.get("package_id", "")),
        file_count=len(package.files),
        scene_count=scene_count,
        issues=tuple(issues),
    )


def assert_package_ok(report: PackageValidationReport) -> None:
    """Raise when a package must not be published."""

    if report.ok:
        return
    detail = "; ".join(f"{i.code}: {i.message}" for i in report.errors)
    raise PublicationBlockedError(f"package invalid: {detail}")


__all__ = [
    "LESSON_PLAN_REQUIRED_FIELDS",
    "LESSON_SECTION_REQUIRED_FIELDS",
    "LESSON_SECTION_TYPES",
    "MANIFEST_ALLOWED_FIELDS",
    "MANIFEST_FILE_REQUIRED_FIELDS",
    "MANIFEST_REQUIRED_FIELDS",
    "PackageValidationReport",
    "assert_package_ok",
    "validate_package",
]
