"""Deterministic test double for the renderer capability.

``docs/providers/DOCUMENT_RENDERER.md`` requires every capability to expose a
*test double*. This one reproduces the failure modes the fidelity gate cares
about — permanent failure, transient failure (bounded retry), degraded output,
unsupported objects, and a raising renderer — without any I/O.
"""

from __future__ import annotations

from typing import Optional

from app.compiler.models.ir import (
    FIDELITY_DEGRADED,
    FIDELITY_STRUCTURAL,
    SlideScene,
)
from app.compiler.renderers.base import (
    CancelToken,
    CapabilityReport,
    DocumentRenderer,
    RenderBudget,
    RenderConfig,
    RenderErrorCode,
    RenderRequest,
    RenderStatus,
    RendererError,
    SceneRender,
)


class FakeRenderer(DocumentRenderer):
    renderer_id = "fake-renderer"
    renderer_version = "1.0.0"
    engine = "fake"

    def __init__(
        self,
        *,
        config: Optional[RenderConfig] = None,
        object_store=None,
        supported_kinds: Optional[tuple[str, ...]] = None,
        fidelity_ceiling: str = FIDELITY_STRUCTURAL,
        fail_orders: tuple[int, ...] = (),
        fail_code: RenderErrorCode = RenderErrorCode.RENDER_FAILED,
        transient_failures: int = 0,
        degrade_orders: tuple[int, ...] = (),
        raise_code: Optional[RenderErrorCode] = None,
    ) -> None:
        super().__init__(config=config, object_store=object_store)
        if supported_kinds is not None:
            self.supported_kinds = tuple(supported_kinds)
        self.fidelity_ceiling = fidelity_ceiling
        self._fail_orders = frozenset(fail_orders)
        self._fail_code = fail_code
        self._transient_failures = transient_failures
        self._degrade_orders = frozenset(degrade_orders)
        self._raise_code = raise_code
        self._attempts_seen: dict[int, int] = {}

    def inspect_support(self) -> CapabilityReport:
        return CapabilityReport(
            supports=True,
            engine=self.engine,
            version=self.renderer_version,
            fidelity_ceiling=self.fidelity_ceiling,
            supported_kinds=self.supported_kinds,
            available_fonts=tuple(sorted(self.config.available_fonts)),
            reasons=("test double",),
        )

    def _attempt_scene(
        self,
        request: RenderRequest,
        scene: SlideScene,
        token: CancelToken,
        budget: RenderBudget,
    ) -> SceneRender:
        """One attempt: permanent failure, transient failure, or a fake render."""

        if token.cancelled:
            return self._cancelled(scene, "render cancelled")
        if budget.expired():
            return self._failed(scene, RenderErrorCode.RENDER_TIMEOUT, "render deadline exceeded")
        if self._raise_code is not None:
            raise RendererError(self._raise_code, "fake renderer raised")

        seen = self._attempts_seen.get(scene.order, 0)
        self._attempts_seen[scene.order] = seen + 1

        if scene.order in self._fail_orders:
            return self._failed(scene, self._fail_code, "fake permanent failure")
        if seen < self._transient_failures:
            return self._failed(
                scene, RenderErrorCode.RENDER_TIMEOUT, f"fake transient failure {seen + 1}"
            )

        payload = f'<svg><rect data-order="{scene.order}"/></svg>'.encode("utf-8")
        asset_ref = (
            self._persist_asset(payload, "svg")
            if self.object_store is not None
            else f"fake://scene/{scene.order}"
        )
        missing = self.missing_fonts(scene)
        unsupported = self.unsupported_kinds(scene)
        fidelity = self.classify(missing_fonts=missing, unsupported_kinds=unsupported)
        if scene.order in self._degrade_orders:
            fidelity = FIDELITY_DEGRADED
        warnings: list[str] = []
        if missing:
            warnings.append("MISSING_FONT:" + ",".join(missing))
        if unsupported:
            warnings.append("UNSUPPORTED_OBJECT:" + ",".join(unsupported))
        if fidelity == FIDELITY_DEGRADED:
            warnings.append("fidelity degraded; meaning requires review")
        return SceneRender(
            order=scene.order,
            scene_id=scene.scene_id,
            status=RenderStatus.RENDERED,
            fidelity=fidelity,
            asset_ref=asset_ref,
            asset_bytes=len(payload),
            renderer=request.identity,
            fonts_used=tuple(scene.fonts()),
            missing_fonts=missing,
            warnings=tuple(warnings),
        )
