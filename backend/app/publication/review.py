"""Read-only teacher review projection of a Baseline Content Package (V0-007).

The teacher review page needs, for one built package: the per-slide render, the
extracted text, the speaker notes, the warnings/fidelity, and the lesson order
with its safe markers (``DEC-CONTENT-006``, ``DEC-CONTENT-008``).

Everything here is projected **from the package itself** — the artifact under
review — not from the live Content IR or from a fresh render pass. That has three
consequences that matter:

* what the teacher reviews is exactly what the runtime would receive;
* browsing a deck costs no rendering (the expensive stage ran once at build time);
* the projection is a pure function of the stored bytes, so it is deterministic.

Nothing in this module writes, and it must stay that way: it is the *projection*
half of the teacher review. The write half — the approve/reject decision and
draft lesson-order revisions — is :mod:`app.publication.workflow`, and it records
state *about* a package, never content of it. The package under review is
byte-identical before and after any review action (``DEC-CONTENT-004``), and the
publication transition (``APPROVED`` → … → ``PUBLISHED``) is V0-008.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.common.errors import NotFoundError
from app.compiler.models.ir import FIDELITY_DEGRADED, FIDELITY_VALUES
from app.compiler.package_builder.loader import LoadedPackage, read_package
from app.compiler.package_builder.service import PackageBuildService
from app.courses.repository import CourseRepository
from app.storage.object_store import ObjectStore

#: Review states. ``READY``/``REVIEW_REQUIRED`` mirror
#: ``CourseVersionStatus``; ``BLOCKED`` means the package must not be offered at
#: all (the fidelity gate refused to build it). They map onto the review outcomes
#: of ``docs/architecture/07_PUBLICATION_AND_REVIEW.md``: ``READY`` =
#: auto-allowed, ``REVIEW_REQUIRED`` = human-required, ``BLOCKED`` = blocked.
STATE_READY = "READY"
STATE_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATE_BLOCKED = "BLOCKED"

MISSING_FONT_PREFIX = "MISSING_FONT:"

#: Renderer identity whose output is a *re-layout* (V0-019) rather than a
#: reproduction of the source slide.
THEMED_RENDERER_ID = "mentora-themed-svg"

#: ``DEC-TECH-005`` is OPEN: no production renderer has been decided. The
#: **default** mode (V0-019) keeps the author's grouping and re-lays the content
#: out in the platform theme, so the UI must say plainly which part is whose.
THEMED_RENDER_NOTICE = (
    "Slides are re-laid out by the platform in the Mentora theme (its layout, "
    "typeface, palette and page number): the deck's grouping and content are the "
    "author's, the arrangement within each group and the appearance are the "
    "platform's. No native PowerPoint render is produced; a production renderer "
    "technology is still an open decision (DEC-TECH-005)."
)

#: ``RENDER_PLACEHOLDER_NOTICE`` (V0-018) describes the ``faithful`` mode.
RENDER_PLACEHOLDER_NOTICE = (
    "Structural SVG render reproduced from the slide's own styling — not a "
    "native PowerPoint render. A production renderer technology is still an "
    "open decision (DEC-TECH-005)."
)


def render_notice(renderer_name: Optional[str]) -> str:
    """The honest disclosure for the renderer that produced the package."""

    return THEMED_RENDER_NOTICE if renderer_name == THEMED_RENDERER_ID else RENDER_PLACEHOLDER_NOTICE


@dataclass(frozen=True)
class ReviewScene:
    """One slide as the teacher sees it, straight from the package."""

    order: int
    scene_id: str
    fidelity: Optional[str]
    render_status: str
    fallback_asset: Optional[str]
    render_url: Optional[str]
    requires_review: bool
    missing_fonts: tuple[str, ...]
    warnings: tuple[str, ...]
    notes: Optional[str]
    text: tuple[str, ...]
    object_count: int
    step_count: int
    renderer: Optional[dict[str, str]] = None
    source_ref: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "scene_id": self.scene_id,
            "fidelity": self.fidelity,
            "render_status": self.render_status,
            "fallback_asset": self.fallback_asset,
            "render_url": self.render_url,
            "requires_review": self.requires_review,
            "missing_fonts": list(self.missing_fonts),
            "warnings": list(self.warnings),
            "notes": self.notes,
            "text": list(self.text),
            "object_count": self.object_count,
            "step_count": self.step_count,
            "renderer": self.renderer,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True)
class ReviewSection:
    """One entry of the fallback lesson order (``DEC-CONTENT-007``/``008``)."""

    order: int
    section_id: str
    type: str
    scene_id: Optional[str]
    scene_step_id: Optional[str]
    safe_markers: tuple[str, ...]
    script: Optional[str]
    scene_fidelity: Optional[str] = None
    requires_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "section_id": self.section_id,
            "type": self.type,
            "scene_id": self.scene_id,
            "scene_step_id": self.scene_step_id,
            "safe_markers": list(self.safe_markers),
            "script": self.script,
            "scene_fidelity": self.scene_fidelity,
            "requires_review": self.requires_review,
        }


@dataclass(frozen=True)
class ReviewPackage:
    """The whole review payload for one package."""

    artifact_id: str
    package_id: str
    prefix: str
    course_id: str
    course_version: str
    content_package_version: str
    lesson_plan_version: Optional[str]
    knowledge_index_version: str
    teaching_graph_version: Optional[str]
    created_at: str
    state: str
    publishable: bool
    requires_review: bool
    scene_count: int
    file_count: int
    renderer: Optional[dict[str, str]]
    placeholder_notice: str
    lesson_order: tuple[ReviewSection, ...]
    scenes: tuple[ReviewScene, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "package_id": self.package_id,
            "prefix": self.prefix,
            "course_id": self.course_id,
            "course_version": self.course_version,
            "content_package_version": self.content_package_version,
            "lesson_plan_version": self.lesson_plan_version,
            "knowledge_index_version": self.knowledge_index_version,
            "teaching_graph_version": self.teaching_graph_version,
            "created_at": self.created_at,
            "state": self.state,
            "publishable": self.publishable,
            "requires_review": self.requires_review,
            "scene_count": self.scene_count,
            "file_count": self.file_count,
            "renderer": self.renderer,
            "placeholder_notice": self.placeholder_notice,
            "lesson_order": [section.to_dict() for section in self.lesson_order],
            "scenes": [scene.to_dict() for scene in self.scenes],
        }


class ReviewService:
    """Builds and serves the teacher review view of one artifact."""

    def __init__(
        self,
        repository: CourseRepository,
        object_store: ObjectStore,
        package_service: PackageBuildService,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._packages = package_service

    # -- write once (the expensive path) -------------------------------------------
    def build_review(self, institution_id: str, artifact_id: str) -> ReviewPackage:
        """Build the package (idempotent) and return its review projection.

        The package builder enforces the fidelity gate, so a document with a
        ``FAILED``/``CANCELLED``/missing render raises ``PUBLICATION_BLOCKED``
        here and can never be offered for review.
        """

        self._packages.build(institution_id, artifact_id)
        review = self.load_review(institution_id, artifact_id)
        if review is None:  # pragma: no cover - build() just wrote the manifest
            raise NotFoundError(f"package for artifact {artifact_id} was not stored")
        return review

    # -- read many (the cheap path) ------------------------------------------------
    def load_review(self, institution_id: str, artifact_id: str) -> Optional[ReviewPackage]:
        """Project the stored package, or ``None`` when it has not been built."""

        loaded = self._load(institution_id, artifact_id)
        if loaded is None:
            return None
        return self._project(artifact_id, loaded)

    def scene_svg(self, institution_id: str, artifact_id: str, order: int) -> bytes:
        """The packaged fallback render for one slide — no re-rendering.

        The bytes come from the package's own asset file, and only after the
        manifest confirms that the scene's ``fallback_asset`` is a file the
        package lists (so a caller can never address an arbitrary path).
        """

        loaded = self._load(institution_id, artifact_id)
        if loaded is None:
            raise NotFoundError(
                f"no package has been built for artifact {artifact_id}; "
                "build the review package first"
            )
        scene = loaded.scene_for_order(order)
        if scene is None:
            raise NotFoundError(f"package has no scene {order}")
        asset = scene.get("fallback_asset")
        if not isinstance(asset, str) or not asset.startswith("assets/"):
            raise NotFoundError(f"scene {order} has no packaged fallback asset")
        return loaded.data(asset)

    # -- internals -----------------------------------------------------------------
    def _load(self, institution_id: str, artifact_id: str) -> Optional[LoadedPackage]:
        # Tenant-scoped: another institution's artifact raises before any read.
        prefix = self._packages.package_prefix_for(institution_id, artifact_id)
        return read_package(self._object_store, prefix)

    def _project(self, artifact_id: str, loaded: LoadedPackage) -> ReviewPackage:
        manifest = loaded.manifest
        scenes: list[ReviewScene] = []
        for path in loaded.scene_paths():
            document = loaded.data_json(path)
            scenes.append(self._project_scene(artifact_id, document))
        scenes.sort(key=lambda scene: scene.order)

        by_scene = {scene.scene_id: scene for scene in scenes}
        plan = loaded.lesson_plan() or {}

        requires_review = any(scene.requires_review for scene in scenes)
        blocked = any(
            scene.render_status != "RENDERED" or scene.fidelity not in FIDELITY_VALUES
            for scene in scenes
        )
        if blocked:
            state = STATE_BLOCKED
        elif requires_review:
            state = STATE_REVIEW_REQUIRED
        else:
            state = STATE_READY

        renderer = self._renderer_identity(scenes)

        return ReviewPackage(
            artifact_id=artifact_id,
            package_id=str(manifest.get("package_id", "")),
            prefix=loaded.prefix,
            course_id=str(manifest.get("course_id", "")),
            course_version=str(manifest.get("course_version", "")),
            content_package_version=str(manifest.get("content_package_version", "")),
            lesson_plan_version=plan.get("lesson_plan_version"),
            knowledge_index_version=str(manifest.get("knowledge_index_version", "")),
            teaching_graph_version=manifest.get("teaching_graph_version"),
            created_at=str(manifest.get("created_at", "")),
            state=state,
            publishable=state != STATE_BLOCKED,
            requires_review=requires_review,
            scene_count=len(scenes),
            file_count=len(manifest.get("files") or []),
            renderer=renderer,
            placeholder_notice=render_notice(renderer.get("name") if renderer else None),
            lesson_order=self._project_lesson_order(plan, by_scene),
            scenes=tuple(scenes),
        )

    @staticmethod
    def _project_scene(artifact_id: str, document: dict[str, Any]) -> ReviewScene:
        warnings = tuple(str(w) for w in (document.get("warnings") or []))
        # ``MISSING_FONT:<family>`` is the renderer's greppable degradation
        # signal; the review surfaces it as a first-class field.
        missing_fonts = tuple(
            w[len(MISSING_FONT_PREFIX) :] for w in warnings if w.startswith(MISSING_FONT_PREFIX)
        )
        fidelity = document.get("fidelity")
        asset = document.get("fallback_asset")
        # A scene is only in a package if it rendered, and a render always has an
        # asset; anything else is reported as failed rather than as a blank frame.
        render_status = "RENDERED" if asset else "FAILED"
        requires_review = fidelity == FIDELITY_DEGRADED or bool(missing_fonts)

        text: list[str] = []
        objects = document.get("objects") or []
        for obj in objects:
            for paragraph in obj.get("paragraphs") or []:
                value = str(paragraph.get("text", ""))
                if value.strip():
                    text.append(value)

        order = int(document.get("order", 0))
        renderer = document.get("renderer")
        return ReviewScene(
            order=order,
            scene_id=str(document.get("scene_id", "")),
            fidelity=fidelity,
            render_status=render_status,
            fallback_asset=asset,
            render_url=f"/artifacts/{artifact_id}/review-package/renders/{order}",
            requires_review=requires_review,
            missing_fonts=missing_fonts,
            warnings=warnings,
            notes=document.get("notes"),
            text=tuple(text),
            object_count=len(objects),
            step_count=len(document.get("steps") or []),
            renderer=dict(renderer) if isinstance(renderer, dict) else None,
            source_ref=document.get("source_ref") or {},
        )

    @staticmethod
    def _renderer_identity(scenes: tuple[ReviewScene, ...]) -> Optional[dict[str, str]]:
        """The renderer identity recorded in the package (``DEC-CONTENT-006``)."""

        for scene in scenes:
            if scene.renderer:
                return scene.renderer
        return None

    @staticmethod
    def _project_lesson_order(
        plan: dict[str, Any], by_scene: dict[str, ReviewScene]
    ) -> tuple[ReviewSection, ...]:
        sections: list[ReviewSection] = []
        for index, section in enumerate(plan.get("sections") or []):
            scene_id = section.get("scene_id")
            scene = by_scene.get(scene_id) if isinstance(scene_id, str) else None
            sections.append(
                ReviewSection(
                    order=index,
                    section_id=str(section.get("section_id", "")),
                    type=str(section.get("type", "")),
                    scene_id=scene_id,
                    scene_step_id=section.get("scene_step_id"),
                    safe_markers=tuple(str(m) for m in (section.get("safe_markers") or [])),
                    script=section.get("script"),
                    scene_fidelity=scene.fidelity if scene else None,
                    requires_review=scene.requires_review if scene else False,
                )
            )
        return tuple(sections)


__all__ = [
    "MISSING_FONT_PREFIX",
    "RENDER_PLACEHOLDER_NOTICE",
    "STATE_BLOCKED",
    "STATE_READY",
    "STATE_REVIEW_REQUIRED",
    "THEMED_RENDERER_ID",
    "THEMED_RENDER_NOTICE",
    "ReviewPackage",
    "ReviewScene",
    "ReviewSection",
    "ReviewService",
    "render_notice",
]
