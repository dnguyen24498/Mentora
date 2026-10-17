"""Scene/fidelity validation and the publication gate (V0-005).

Acceptance criteria implemented here:

* **Every slide has a render or an explicit FAILED** — a scene without a render
  result is a hard error, so "no render" can never be mistaken for "fine".
* **FAILED blocks publication** — ``publishable`` is False whenever any scene
  failed, was cancelled, or is missing.
* **Same engine/config gives stable logical output** — determinism itself is
  asserted in the renderer tests; this module asserts the *document* invariants
  that make a render trustworthy (``DEC-CONTENT-006``: every scene has explicit
  fidelity, renderer identity, warnings, and provenance).

Only the *shape* of a scene is checked (``contracts/ctf/scene.schema.json``
required fields) — a hand-rolled check, because adding a JSON-Schema library
would be a new production dependency and no ADR accepts one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.compiler.models.ir import (
    FIDELITY_REQUIRES_REVIEW,
    FIDELITY_VALUES,
    ContentIRDocument,
    SlideScene,
)
from app.compiler.renderers.base import RenderReport, RenderStatus, SceneRender

SEVERITY_ERROR = "error"
SEVERITY_REVIEW = "review"
SEVERITY_WARNING = "warning"

#: ``contracts/ctf/scene.schema.json`` -> ``Scene.required``.
SCENE_REQUIRED_FIELDS = (
    "scene_id",
    "source_ref",
    "order",
    "dimensions",
    "fallback_asset",
    "fidelity",
    "objects",
    "steps",
    "provenance",
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = SEVERITY_ERROR
    scene_order: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "scene_order": self.scene_order,
        }


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    publishable: bool
    requires_review: bool
    scene_count: int
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == SEVERITY_ERROR)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "publishable": self.publishable,
            "requires_review": self.requires_review,
            "scene_count": self.scene_count,
            "issues": [i.to_dict() for i in self.issues],
        }


def _check_scene_shape(scene: SlideScene, issues: list[ValidationIssue]) -> None:
    """Minimal required-field check against the CTF scene schema."""

    data = scene.to_dict()
    for name in SCENE_REQUIRED_FIELDS:
        if name not in data:
            issues.append(
                ValidationIssue(
                    code="MISSING_SCENE_FIELD",
                    message=f"scene field {name!r} is absent",
                    scene_order=scene.order,
                )
            )
    dimensions = data.get("dimensions") or {}
    if not dimensions.get("width") or not dimensions.get("height"):
        issues.append(
            ValidationIssue(
                code="INVALID_SCENE_DIMENSIONS",
                message="scene dimensions must be positive",
                scene_order=scene.order,
            )
        )


def _check_render(
    scene: SlideScene, render: Optional[SceneRender], issues: list[ValidationIssue]
) -> None:
    if render is None:
        # The explicit requirement: a slide is never silently render-less.
        issues.append(
            ValidationIssue(
                code="MISSING_RENDER",
                message="scene has no render result",
                scene_order=scene.order,
            )
        )
        return

    if render.status is RenderStatus.CANCELLED:
        issues.append(
            ValidationIssue(
                code="RENDER_CANCELLED",
                message="render was cancelled; document is incomplete",
                scene_order=scene.order,
            )
        )
        return

    if render.status is RenderStatus.FAILED:
        issues.append(
            ValidationIssue(
                code="RENDER_FAILED",
                message=(
                    f"render failed ({render.error_code.value if render.error_code else 'unknown'})"
                    f": {render.error_message or ''}".rstrip()
                ),
                scene_order=scene.order,
            )
        )
        return

    if not render.asset_ref:
        issues.append(
            ValidationIssue(
                code="MISSING_FALLBACK_ASSET",
                message="rendered scene has no fallback asset",
                scene_order=scene.order,
            )
        )
    if render.renderer is None:
        issues.append(
            ValidationIssue(
                code="MISSING_RENDERER_IDENTITY",
                message="rendered scene has no renderer identity (DEC-CONTENT-006)",
                scene_order=scene.order,
            )
        )
    if render.fidelity not in FIDELITY_VALUES:
        issues.append(
            ValidationIssue(
                code="INVALID_FIDELITY",
                message=f"fidelity {render.fidelity!r} is not one of {sorted(FIDELITY_VALUES)}",
                scene_order=scene.order,
            )
        )
    if render.fidelity in FIDELITY_REQUIRES_REVIEW:
        issues.append(
            ValidationIssue(
                code="DEGRADED_REQUIRES_REVIEW",
                message=f"fidelity {render.fidelity} requires review",
                severity=SEVERITY_REVIEW,
                scene_order=scene.order,
            )
        )
    if render.missing_fonts:
        # V0-019 v5: an unavailable source font is *substituted* with the platform
        # stack and the run is drawn in place, so it is disclosed as a warning
        # rather than being escalated to a human review.
        issues.append(
            ValidationIssue(
                code="FONT_SUBSTITUTED",
                message=(
                    "source fonts substituted with the platform stack: "
                    + ", ".join(render.missing_fonts)
                ),
                severity=SEVERITY_WARNING,
                scene_order=scene.order,
            )
        )


def validate_render(
    document: ContentIRDocument, report: Optional[RenderReport] = None
) -> ValidationReport:
    """Validate a rendered document against the fidelity gate."""

    issues: list[ValidationIssue] = []

    if not document.slides:
        issues.append(
            ValidationIssue(
                code="NO_SLIDES",
                message="document has no slides; refusing to consider it publishable",
            )
        )

    for scene in document.slides:
        _check_scene_shape(scene, issues)
        render = report.scene(scene.order) if report is not None else None
        if render is not None and render.scene_id != scene.scene_id:
            issues.append(
                ValidationIssue(
                    code="SCENE_ID_MISMATCH",
                    message=f"render for scene {scene.order} references {render.scene_id!r}",
                    scene_order=scene.order,
                )
            )
        _check_render(scene, render, issues)

    if report is not None:
        orders = [r.order for r in report.results]
        if len(orders) != len(set(orders)):
            issues.append(
                ValidationIssue(code="DUPLICATE_RENDER", message="the same scene was rendered twice")
            )
        expected = [s.order for s in document.slides]
        for order in expected:
            if order not in orders:
                issues.append(
                    ValidationIssue(
                        code="MISSING_RENDER",
                        message="scene has no render result",
                        scene_order=order,
                    )
                )
        if report.cancelled:
            issues.append(
                ValidationIssue(
                    code="RENDER_INCOMPLETE",
                    message="render pass was cancelled before covering every scene",
                )
            )

    errors = [i for i in issues if i.severity == SEVERITY_ERROR]
    review = [i for i in issues if i.severity == SEVERITY_REVIEW]
    return ValidationReport(
        ok=not errors,
        publishable=not errors,
        requires_review=bool(review),
        scene_count=len(document.slides),
        issues=tuple(issues),
    )


def assert_publishable(report: ValidationReport) -> None:
    """Raise when a document must not be published.

    Publication itself is V0-008; this is the gate it must call so that
    "FAILED blocks publication" is enforced in one place.
    """

    if report.publishable:
        return
    from app.common.errors import PublicationBlockedError

    detail = "; ".join(f"{i.code}: {i.message}" for i in report.errors)
    raise PublicationBlockedError(f"publication blocked: {detail}")
