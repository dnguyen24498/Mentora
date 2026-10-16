"""Baseline package builder (V0-006).

Maps the rendered Content IR into an immutable Baseline Content Package:
scenes, copied assets, a fallback lesson order with safe segment markers, and a
manifest with checksums.

``DEC-CONTENT-002``: this stage is deterministic and needs no Vision AI and no
Teaching Graph — it is pure data mapping over what V0-004/V0-005 already
produced. The built package therefore contains no source document and, by
construction, no way to reach an OOXML parser (``DEC-CONTENT-001``).

Reference model (``DEC-CONTENT-004``): the manifest is a *reference* envelope.
Every reference inside the package is package-relative — a scene's
``fallback_asset`` is the packaged asset path (``assets/<sha256>.svg``), never
the compiler's internal asset-store key (``renders/<sha256>.svg``), so a
consumer resolves everything against the manifest alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Mapping, Optional

from app.common.errors import AppError, ErrorCode
from app.compiler.models.ir import EXTRACTOR_VERSION, ContentIRDocument, SlideScene
from app.compiler.package_builder.layout import (
    MANIFEST_SCHEMA_VERSION,
    MEDIA_TYPE_JSON,
    UNINDEXED,
    asset_path,
    extension_of,
    lesson_plan_path,
    media_type_for,
    scene_path,
)
from app.compiler.package_builder.models import (
    STEP_KIND_ALL_VISIBLE,
    BaselinePackage,
    LessonPlan,
    LessonSection,
    PackageFile,
    PackageMetadata,
    SceneStep,
)

#: Baseline section types (``contracts/ctf/lesson-plan.schema.json`` enum).
SECTION_TYPE_EXPLANATION = "EXPLANATION"
SECTION_TYPE_MEDIA = "MEDIA"


class PackageBuildError(AppError):
    """The IR cannot become a package (no scenes, missing asset, bad reference).

    ``issue_code`` carries the precise, stable classification; the HTTP status is
    ``409`` (the document exists but cannot be packaged as-is). ``ErrorCode``
    reuses the existing ``INVALID_REQUEST`` because ``app/common/errors.py`` is
    outside this task's writable area — precise classification is carried by
    ``issue_code`` and by ``PackageValidationReport`` issue codes, matching the
    design of the fidelity validator (``validators/fidelity.py``).
    """

    code = ErrorCode.INVALID_REQUEST
    http_status = 409

    def __init__(self, message: str, *, issue_code: str = "INVALID_PACKAGE") -> None:
        super().__init__(message)
        self.issue_code = issue_code


def content_package_version(
    source_sha256: str, *, config_hash: str, compiler_version: str = EXTRACTOR_VERSION
) -> str:
    """Deterministic content-package version.

    ``docs/architecture/04_CONTENT_COMPILER.md``: *"Deterministic cache key uses
    source checksum, compiler version, and config hash."* The same triple always
    yields the same version string, so rebuilding unchanged content is
    recognisably identical (and a rebuild with a different renderer config is
    recognisably different).
    """

    key = f"{source_sha256}:{compiler_version}:{config_hash}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"cpv-{digest[:16]}"


def lesson_plan_version_for(content_version: str) -> str:
    """Version of the baseline lesson plan, derived from the same cache key."""

    digest = hashlib.sha256(f"lesson:{content_version}".encode("utf-8")).hexdigest()
    return f"lp-{digest[:16]}"


def package_id_for(content_version: str) -> str:
    """Deterministic package id.

    The identity of an immutable content package *is* its content version, so a
    retried or repeated build targets the same storage prefix: an interrupted
    build is completed by re-running it, and unchanged content never accumulates
    duplicate packages. It also lets a read-only consumer (teacher review,
    publication) address a package without keeping server state.
    """

    return f"pkg-{content_version.removeprefix('cpv-')}"


def build_steps(scene: SlideScene) -> tuple[SceneStep, ...]:
    """Reveal steps for one scene.

    ``DEC-CONTENT-007`` requires instructional reveal order to be preserved as
    discrete scene steps. V0-004 extracts no animation or timing data, so the
    baseline emits exactly one step in which every object is visible, ordered by
    the extractor's reading order. Objects are never dropped or reordered.
    """

    ordered = sorted(scene.objects, key=lambda obj: obj.reading_order)
    return (
        SceneStep(
            step_id=f"{scene.scene_id}#step-0",
            order=0,
            kind=STEP_KIND_ALL_VISIBLE,
            object_ids=tuple(obj.source_id for obj in ordered),
        ),
    )


def _scene_has_text(scene: SlideScene) -> bool:
    return any(paragraph.text.strip() for obj in scene.objects for paragraph in obj.paragraphs)


def section_type_for(scene: SlideScene) -> str:
    """Baseline section type: text-bearing scenes explain, the rest are media."""

    return SECTION_TYPE_EXPLANATION if _scene_has_text(scene) else SECTION_TYPE_MEDIA


def build_lesson_plan(
    document: ContentIRDocument,
    *,
    lesson_id: str,
    lesson_plan_version: str,
    steps_by_scene: Mapping[str, tuple[SceneStep, ...]],
) -> LessonPlan:
    """Fallback lesson order: one section per scene, in scene order.

    Speaker notes become the section ``script`` — ``DEC-CONTENT-008`` treats them
    as weighted evidence, so they are carried verbatim and never paraphrased. A
    scene without notes still yields a usable section (``script: null``).
    """

    ordered = sorted(document.slides, key=lambda scene: scene.order)
    sections: list[LessonSection] = []
    for index, scene in enumerate(ordered):
        steps = steps_by_scene.get(scene.scene_id, ())
        sections.append(
            LessonSection(
                section_id=f"{lesson_id}#section-{index}",
                type=section_type_for(scene),
                safe_markers=tuple(step.step_id for step in steps),
                scene_id=scene.scene_id,
                # A section enters its scene at the first step; every step id is
                # also a safe marker the runtime may pause at.
                scene_step_id=steps[0].step_id if steps else None,
                script=scene.notes,
                fallback_script=None,
                concept_id=None,
            )
        )
    return LessonPlan(
        lesson_plan_version=lesson_plan_version, lesson_id=lesson_id, sections=tuple(sections)
    )


def scene_payload(
    scene: SlideScene, steps: tuple[SceneStep, ...], *, fallback_asset: str
) -> dict[str, Any]:
    """One CTF scene document (``contracts/ctf/scene.schema.json``).

    ``fallback_asset`` is rewritten to the package-relative asset path so the
    scene document has no dependency on the compiler's asset store.
    """

    return replace(
        scene,
        steps=[step.to_dict() for step in steps],
        fallback_asset=fallback_asset,
    ).to_dict()


class PackageBuilder:
    """Turns a rendered document into a :class:`BaselinePackage`.

    The builder is pure: it takes the already-rendered document plus the bytes of
    every asset it needs, and returns the package. It never renders, never reads
    the source document, and never consults a provider.
    """

    def build(
        self,
        document: ContentIRDocument,
        *,
        metadata: PackageMetadata,
        assets: Mapping[str, bytes],
    ) -> BaselinePackage:
        scenes = sorted(document.slides, key=lambda scene: scene.order)
        if not scenes:
            raise PackageBuildError("document has no scenes", issue_code="NO_SCENES")

        seen_ids: set[str] = set()
        for scene in scenes:
            if scene.scene_id in seen_ids:
                raise PackageBuildError(
                    f"duplicate scene_id {scene.scene_id!r}", issue_code="DUPLICATE_SCENE_ID"
                )
            seen_ids.add(scene.scene_id)
            if not scene.fallback_asset:
                # A failed render must block publication, never enter a package.
                raise PackageBuildError(
                    f"scene {scene.order} has no fallback asset",
                    issue_code="MISSING_FALLBACK_ASSET",
                )

        # Copy assets into the package, deduplicated by content address, so two
        # scenes that share a render contribute one file.
        packaged_assets: dict[str, PackageFile] = {}
        for scene in scenes:
            assert scene.fallback_asset is not None  # checked above
            if scene.fallback_asset in packaged_assets:
                continue
            data = assets.get(scene.fallback_asset)
            if data is None:
                raise PackageBuildError(
                    f"asset {scene.fallback_asset!r} referenced by scene"
                    f" {scene.order} is missing",
                    issue_code="MISSING_ASSET",
                )
            digest = hashlib.sha256(data).hexdigest()
            path = asset_path(digest, extension_of(scene.fallback_asset))
            packaged_assets[scene.fallback_asset] = PackageFile(
                path=path, media_type=media_type_for(path), data=data
            )

        steps_by_scene = {scene.scene_id: build_steps(scene) for scene in scenes}

        files: list[PackageFile] = []
        for scene in scenes:
            assert scene.fallback_asset is not None  # checked above
            payload = scene_payload(
                scene,
                steps_by_scene[scene.scene_id],
                fallback_asset=packaged_assets[scene.fallback_asset].path,
            )
            files.append(
                PackageFile(
                    path=scene_path(scene.order, scene.scene_id),
                    media_type=MEDIA_TYPE_JSON,
                    data=_json_bytes(payload),
                )
            )

        lesson_plan = build_lesson_plan(
            document,
            lesson_id=metadata.lesson_id,
            lesson_plan_version=metadata.lesson_plan_version,
            steps_by_scene=steps_by_scene,
        )
        files.append(
            PackageFile(
                path=lesson_plan_path(),
                media_type=MEDIA_TYPE_JSON,
                data=_json_bytes(lesson_plan.to_dict()),
            )
        )
        files.extend(packaged_assets.values())

        # Deterministic manifest: files sorted by path, keys sorted on write.
        files.sort(key=lambda package_file: package_file.path)
        return BaselinePackage(
            manifest=self._manifest(metadata, files), files=tuple(files)
        )

    @staticmethod
    def _manifest(metadata: PackageMetadata, files: list[PackageFile]) -> dict[str, Any]:
        """The immutable envelope (``contracts/ctf/manifest.schema.json``).

        Exactly the schema's properties: the schema sets
        ``additionalProperties: false``, so review/publish state is reported by
        the validator (``validators/package.py``) rather than being smuggled into
        the manifest, and the manifest is never listed in its own ``files[]``
        (``DEC-CONTENT-004``).
        """

        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "package_id": metadata.package_id,
            "tenant_id": metadata.tenant_id,
            "course_id": metadata.course_id,
            "course_version": metadata.course_version,
            "content_package_version": metadata.content_package_version,
            "teaching_graph_version": metadata.teaching_graph_version,
            "lesson_plan_versions": [metadata.lesson_plan_version],
            "knowledge_index_version": metadata.knowledge_index_version or UNINDEXED,
            "files": [package_file.to_manifest_entry() for package_file in files],
            "created_at": metadata.created_at,
        }


def _json_bytes(payload: Any) -> bytes:
    """Canonical JSON bytes: sorted keys, stable indentation, UTF-8."""

    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")


def resolve_assets(
    document: ContentIRDocument, *, get: Any, missing: Optional[type[Exception]] = None
) -> dict[str, bytes]:
    """Read every asset the document references through ``get(key)``.

    ``get`` is any ``Callable[[str], bytes]`` (in practice
    ``ObjectStore.get``). Kept separate from :class:`PackageBuilder` so the
    builder stays pure and testable without a store.
    """

    resolved: dict[str, bytes] = {}
    for scene in document.slides:
        ref = scene.fallback_asset
        if not ref or ref in resolved:
            continue
        try:
            resolved[ref] = get(ref)
        except Exception as exc:  # storage failure -> explicit, classified
            raise PackageBuildError(
                f"cannot read asset {ref!r} for scene {scene.order}: {exc}",
                issue_code="MISSING_ASSET",
            ) from exc
    return resolved


__all__ = [
    "SECTION_TYPE_EXPLANATION",
    "SECTION_TYPE_MEDIA",
    "PackageBuildError",
    "PackageBuilder",
    "build_lesson_plan",
    "build_steps",
    "content_package_version",
    "lesson_plan_version_for",
    "package_id_for",
    "resolve_assets",
    "scene_payload",
    "section_type_for",
]
