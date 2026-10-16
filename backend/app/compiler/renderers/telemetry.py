"""Structured telemetry for the render stage.

``docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md``: propagate tenant,
artifact, correlation and renderer versions while **redacting sensitive text**.
So these records carry counts, durations, fidelity and font *names* — never slide
text or student data.

Metrics are in-process counters. Per-tenant/provider bounded queues and real
queue-depth metrics belong to the job runner (V0-003), which owns admission.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.compiler.renderers.base import RenderReport, RenderStatus

logger = logging.getLogger("mentora.compiler.render")


@dataclass
class RenderMetrics:
    renders_started: int = 0
    renders_completed: int = 0
    renders_cancelled: int = 0
    scenes_rendered: int = 0
    scenes_failed: int = 0
    scenes_cancelled: int = 0
    degraded_scenes: int = 0
    missing_font_scenes: int = 0
    total_render_ms: int = 0
    publish_blocked: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class RenderTelemetry:
    """Emits one structured record per render pass and keeps counters."""

    metrics: RenderMetrics = field(default_factory=RenderMetrics)
    _logger: logging.Logger = field(default=logger, repr=False)

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"event": event, **fields}
        try:
            self._logger.info(json.dumps(record, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - telemetry must not break rendering
            self._logger.info("event=%s", event)
        return record

    def record_render_started(self, *, artifact_id: str, scene_count: int, renderer: Optional[dict]) -> None:
        self.metrics.renders_started += 1
        self.emit(
            "compiler.render.started",
            artifact_id=artifact_id,
            scene_count=scene_count,
            renderer=renderer,
        )

    def record_render_report(
        self,
        *,
        artifact_id: str,
        report: RenderReport,
        institution_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        publishable: Optional[bool] = None,
        requires_review: Optional[bool] = None,
    ) -> dict[str, Any]:
        rendered = [r for r in report.results if r.status is RenderStatus.RENDERED]
        failed = [r for r in report.results if r.status is RenderStatus.FAILED]
        cancelled = [r for r in report.results if r.status is RenderStatus.CANCELLED]

        self.metrics.renders_completed += 0 if report.cancelled else 1
        self.metrics.renders_cancelled += 1 if report.cancelled else 0
        self.metrics.scenes_rendered += len(rendered)
        self.metrics.scenes_failed += len(failed)
        self.metrics.scenes_cancelled += len(cancelled)
        self.metrics.degraded_scenes += sum(
            1 for r in rendered if any("degraded" in w for w in r.warnings)
        )
        self.metrics.missing_font_scenes += sum(1 for r in rendered if r.missing_fonts)
        self.metrics.total_render_ms += report.usage.duration_ms
        if publishable is False:
            self.metrics.publish_blocked += 1

        return self.emit(
            "compiler.render.completed",
            artifact_id=artifact_id,
            institution_id=institution_id,
            trace_id=trace_id,
            renderer=report.renderer.to_dict() if report.renderer else None,
            slides=len(report.results),
            rendered=len(rendered),
            failed=len(failed),
            cancelled=len(cancelled),
            degraded=self.metrics.degraded_scenes,
            missing_fonts=sorted({f for r in rendered for f in r.missing_fonts}),
            error_codes=sorted({r.error_code.value for r in failed if r.error_code}),
            duration_ms=report.usage.duration_ms,
            asset_bytes=report.usage.asset_bytes,
            cost_units=report.usage.cost_units,
            data_region=report.usage.data_region,
            publishable=publishable,
            requires_review=requires_review,
        )

    def record_health(self, *, renderer_name: str, health: dict) -> None:
        self.emit("compiler.renderer.health", renderer=renderer_name, **health)
