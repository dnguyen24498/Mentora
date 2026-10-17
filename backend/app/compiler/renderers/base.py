"""Provider-neutral ``DocumentRenderer`` interface and render result types (V0-005).

``docs/providers/DOCUMENT_RENDERER.md``: *inspect support, render, report
fonts/engine/warnings, cancel/health. Never execute source active content.*
``docs/architecture/19_RELIABILITY_SLO_AND_BACKPRESSURE.md`` /
``DEC-RELIABILITY-001``: *every external capability has deadline, bounded retry,
circuit breaker, admission control, and fallback*, plus stable error
classification, idempotency, usage/cost, data region, and trace propagation.

**The renderer technology is not decided.** ``DEC-TECH-005`` ("Native PowerPoint
rendering deployment and licensing") is OPEN, so ``docs/adr/proposed/
ADR-P005_RENDERER.md`` applies: *"Until accepted, provider-neutral interfaces and
mocks are used."* This module is that interface; ``renderers/structural.py`` is
the deterministic local implementation used in the meantime, and it is reported
as ``STRUCTURAL_RENDERED`` — never as a native/compatible render.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, ClassVar, Mapping, Optional

from app.compiler.models.ir import (
    FIDELITY_DEGRADED,
    FIDELITY_STRUCTURAL,
    ContentIRDocument,
    SlideScene,
)
from app.common.errors import StorageError

#: Deterministic allowlist of font families the local renderer can rely on.
#: Deliberately *not* read from the host: the same document must classify the
#: same way on every machine (``evaluation/manifests/render-fidelity.json``).
DEFAULT_AVAILABLE_FONTS = frozenset(
    {
        "Arial",
        "Calibri",
        "Courier New",
        "DejaVu Sans",
        "Georgia",
        "Helvetica",
        "Liberation Sans",
        "Noto Sans",
        "Segoe UI",
        "Times New Roman",
        "Verdana",
    }
)


class RenderStatus(str, Enum):
    RENDERED = "RENDERED"
    FAILED = "FAILED"
    #: Distinct from FAILED: an interrupted render is retryable and means the
    #: document is *incomplete*, not wrong.
    CANCELLED = "CANCELLED"


class RenderErrorCode(str, Enum):
    """Stable render error classification (never parse the message)."""

    RENDER_TIMEOUT = "RENDER_TIMEOUT"
    RENDER_FAILED = "RENDER_FAILED"
    CORRUPT_INPUT = "CORRUPT_INPUT"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    CANCELLED = "CANCELLED"
    RENDERER_UNAVAILABLE = "RENDERER_UNAVAILABLE"


#: Only these may be retried (``DEC-RELIABILITY-001``: retry transient
#: idempotent work only). Everything else must fail fast so a permanent error
#: cannot loop.
RETRYABLE_CODES = frozenset(
    {RenderErrorCode.RENDER_TIMEOUT, RenderErrorCode.STORAGE_FAILURE}
)


class RendererError(Exception):
    """Raised by a renderer for a non-recoverable, request-level problem."""

    def __init__(self, code: RenderErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class CircuitOpenError(RendererError):
    def __init__(self, message: str = "renderer circuit is open") -> None:
        super().__init__(RenderErrorCode.RENDERER_UNAVAILABLE, message)


# -- configuration --------------------------------------------------------------
@dataclass(frozen=True)
class RenderConfig:
    """Renderer configuration. ``config_hash`` is the determinism key."""

    width_px: int = 1280
    height_px: int = 720
    background: str = "#ffffff"
    #: Fallback family for text whose runs name no known font.
    font_family: str = "sans-serif"
    available_fonts: frozenset[str] = DEFAULT_AVAILABLE_FONTS
    data_region: str = "local"
    deadline_seconds: float = 10.0
    max_attempts: int = 2
    #: Bounded output; a pathological slide must not blow up the object store.
    #: Generous because a faithful render inlines the slide's pictures.
    max_asset_bytes: int = 28 * 1024 * 1024
    #: Upper bound on the *raw* picture bytes one slide may inline (base64 adds
    #: ~1/3). Pictures past the budget render as a labelled placeholder with a
    #: warning instead of failing the scene.
    max_inline_media_bytes: int = 16 * 1024 * 1024
    circuit_failure_threshold: int = 5

    def canonical(self) -> dict:
        return {
            "width_px": self.width_px,
            "height_px": self.height_px,
            "background": self.background,
            "font_family": self.font_family,
            "available_fonts": sorted(self.available_fonts),
            "data_region": self.data_region,
            "deadline_seconds": self.deadline_seconds,
            "max_attempts": self.max_attempts,
            "max_asset_bytes": self.max_asset_bytes,
            "max_inline_media_bytes": self.max_inline_media_bytes,
            "circuit_failure_threshold": self.circuit_failure_threshold,
        }

    def config_hash(self) -> str:
        payload = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# -- deadline / cancellation ----------------------------------------------------
class RenderBudget:
    """End-to-end deadline and retry budget (``DEC-RELIABILITY-001``).

    The clock is injected so timeout behaviour is deterministic in tests
    instead of depending on wall-clock sleeps.
    """

    def __init__(
        self,
        deadline_seconds: float,
        *,
        max_attempts: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self.deadline_seconds = deadline_seconds
        self.max_attempts = max(1, max_attempts)
        self._started_at = clock()
        self._deadline = self._started_at + deadline_seconds

    def elapsed(self) -> float:
        return self._clock() - self._started_at

    def remaining(self) -> float:
        return self._deadline - self._clock()

    def expired(self) -> bool:
        return self._clock() >= self._deadline

    def duration_ms(self) -> int:
        return int(self.elapsed() * 1000)


class CancelToken:
    """Cooperative cancellation flag, safe to set from another thread."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


# -- results --------------------------------------------------------------------
@dataclass(frozen=True)
class RendererIdentity:
    """Who rendered what, with which config — ``DEC-CONTENT-006`` provenance."""

    name: str
    version: str
    engine: str
    config_hash: str
    data_region: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "engine": self.engine,
            "config_hash": self.config_hash,
            "data_region": self.data_region,
        }


@dataclass(frozen=True)
class CapabilityReport:
    """``inspect_support()``: what this renderer can do, before any work starts."""

    supports: bool
    engine: str
    version: str
    fidelity_ceiling: str
    supported_kinds: tuple[str, ...]
    available_fonts: tuple[str, ...]
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "supports": self.supports,
            "engine": self.engine,
            "version": self.version,
            "fidelity_ceiling": self.fidelity_ceiling,
            "supported_kinds": list(self.supported_kinds),
            "available_fonts": list(self.available_fonts),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class SceneRender:
    order: int
    scene_id: str
    status: RenderStatus
    fidelity: Optional[str] = None
    asset_ref: Optional[str] = None
    asset_bytes: int = 0
    renderer: Optional[RendererIdentity] = None
    fonts_used: tuple[str, ...] = ()
    missing_fonts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: Optional[RenderErrorCode] = None
    error_message: Optional[str] = None
    attempts: int = 1
    duration_ms: int = 0

    @property
    def retryable(self) -> bool:
        return self.error_code in RETRYABLE_CODES

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "scene_id": self.scene_id,
            "status": self.status.value,
            "fidelity": self.fidelity,
            "asset_ref": self.asset_ref,
            "asset_bytes": self.asset_bytes,
            "renderer": self.renderer.to_dict() if self.renderer else None,
            "fonts_used": list(self.fonts_used),
            "missing_fonts": list(self.missing_fonts),
            "warnings": list(self.warnings),
            "error": (
                {"code": self.error_code.value, "message": self.error_message, "retryable": self.retryable}
                if self.error_code
                else None
            ),
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class RenderUsage:
    """Usage/cost and region accounting for one render pass."""

    slides_rendered: int = 0
    slides_failed: int = 0
    slides_cancelled: int = 0
    asset_bytes: int = 0
    duration_ms: int = 0
    cost_units: float = 0.0
    data_region: str = "local"

    def to_dict(self) -> dict:
        return {
            "slides_rendered": self.slides_rendered,
            "slides_failed": self.slides_failed,
            "slides_cancelled": self.slides_cancelled,
            "asset_bytes": self.asset_bytes,
            "duration_ms": self.duration_ms,
            "cost_units": self.cost_units,
            "data_region": self.data_region,
        }


@dataclass(frozen=True)
class RenderReport:
    results: tuple[SceneRender, ...]
    usage: RenderUsage
    renderer: Optional[RendererIdentity] = None
    warnings: tuple[str, ...] = ()
    cancelled: bool = False

    def scene(self, order: int) -> Optional[SceneRender]:
        for result in self.results:
            if result.order == order:
                return result
        return None

    def to_dict(self) -> dict:
        return {
            "renderer": self.renderer.to_dict() if self.renderer else None,
            "cancelled": self.cancelled,
            "warnings": list(self.warnings),
            "usage": self.usage.to_dict(),
            "scenes": [r.to_dict() for r in self.results],
        }


@dataclass(frozen=True)
class RendererHealth:
    """Circuit-breaker state and queue metrics for admission control."""

    state: str = "closed"  # closed | open | half_open
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    total_rendered: int = 0
    total_failed: int = 0
    in_flight: int = 0
    max_concurrency: int = 1

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "total_rendered": self.total_rendered,
            "total_failed": self.total_failed,
            "in_flight": self.in_flight,
            "max_concurrency": self.max_concurrency,
        }


@dataclass(frozen=True)
class RenderRequest:
    """Everything a renderer needs, including trace propagation.

    ``media`` carries the bytes of the images the document references, keyed by
    the ``media_ref`` part path already in the IR. They are supplied by the
    compiler — the only component allowed to open the source package
    (``DEC-CONTENT-001``) — so a renderer stays a pure function of its input and
    never reads the original document itself.
    """

    document: ContentIRDocument
    identity: RendererIdentity
    trace_id: Optional[str] = None
    correlation_id: Optional[str] = None
    media: Mapping[str, bytes] = field(default_factory=dict)


class DocumentRenderer(ABC):
    """Replaceable rendering capability (``docs/providers/DOCUMENT_RENDERER.md``).

    Implementations must be deterministic for a fixed ``(document, config)`` and
    must never execute source active content.
    """

    renderer_id: ClassVar[str] = "document-renderer"
    renderer_version: ClassVar[str] = "0.0.0"
    engine: ClassVar[str] = "unknown"

    #: Object kinds a renderer must be able to draw; unknown kinds degrade.
    supported_kinds: ClassVar[tuple[str, ...]] = (
        "text",
        "shape",
        "picture",
        "table",
        "chart",
        "connector",
        "group",
        "graphicFrame",
    )

    @abstractmethod
    def inspect_support(self) -> CapabilityReport:
        """Report engine/version/fidelity ceiling and available fonts."""

    @abstractmethod
    def _attempt_scene(
        self,
        request: RenderRequest,
        scene: SlideScene,
        token: CancelToken,
        budget: RenderBudget,
    ) -> SceneRender:
        """One attempt at rendering a single scene (no retry inside)."""

    @abstractmethod
    def health(self) -> RendererHealth:
        """Circuit-breaker state + queue/concurrency metrics."""

    # -- shared control flow (deadline, cancellation, bounded retry) -------------
    def render(
        self,
        request: RenderRequest,
        *,
        budget: RenderBudget,
        cancel: Optional[CancelToken] = None,
    ) -> RenderReport:
        """Render every scene, within ``budget`` and honouring ``cancel``.

        Bounded retry is applied here so it is identical for every renderer:
        only failures classified retryable are retried, at most
        ``budget.max_attempts`` times, and never past the deadline.
        """

        token = cancel or CancelToken()
        scene_count = len(request.document.slides)

        if self.trip_if_unhealthy():
            # Admission control: do not enqueue more work for a broken renderer.
            raise RendererError(
                RenderErrorCode.RENDERER_UNAVAILABLE,
                f"circuit open after {self._consecutive_failures} consecutive failures",
            )

        self._active_cancel = token
        self._in_flight += 1
        started = time.monotonic()
        results: list[SceneRender] = []
        try:
            for scene in request.document.slides:
                if token.cancelled:
                    results.append(self._cancelled(scene, "render cancelled"))
                    continue
                if budget.expired():
                    results.append(
                        self._failed(scene, RenderErrorCode.RENDER_TIMEOUT, "render deadline exceeded")
                    )
                    continue
                results.append(self._render_scene_with_retry(request, scene, token, budget))
        finally:
            self._in_flight -= 1
            self._active_cancel = None

        for result in results:
            self._record_result(result)

        rendered = [r for r in results if r.status is RenderStatus.RENDERED]
        usage = RenderUsage(
            slides_rendered=len(rendered),
            slides_failed=len([r for r in results if r.status is RenderStatus.FAILED]),
            slides_cancelled=len([r for r in results if r.status is RenderStatus.CANCELLED]),
            asset_bytes=sum(r.asset_bytes for r in rendered),
            duration_ms=int((time.monotonic() - started) * 1000),
            cost_units=0.0,
            data_region=self.config.data_region,
        )
        warnings: list[str] = []
        if any(r.status is RenderStatus.CANCELLED for r in results):
            warnings.append("render cancelled; document is incomplete")
        if len(results) != scene_count:  # pragma: no cover - defensive
            warnings.append("render results do not cover every scene")

        return RenderReport(
            results=tuple(results),
            usage=usage,
            renderer=request.identity,
            warnings=tuple(warnings),
            cancelled=any(r.status is RenderStatus.CANCELLED for r in results),
        )

    def _render_scene_with_retry(
        self, request: RenderRequest, scene: SlideScene, token: CancelToken, budget: RenderBudget
    ) -> SceneRender:
        attempt = 0
        result = self._failed(scene, RenderErrorCode.RENDER_FAILED, "not attempted")
        while True:
            attempt += 1
            result = self._attempt_scene(request, scene, token, budget)
            if result.status is not RenderStatus.FAILED or not result.retryable:
                break
            if attempt >= budget.max_attempts:
                break
            if budget.expired() or token.cancelled:
                break
        return replace(result, attempts=attempt)

    def _failed(
        self, scene: SlideScene, code: RenderErrorCode, message: str
    ) -> SceneRender:
        return SceneRender(
            order=scene.order,
            scene_id=scene.scene_id,
            status=RenderStatus.FAILED,
            renderer=self.identity(),
            error_code=code,
            error_message=message,
        )

    def _cancelled(self, scene: SlideScene, message: str) -> SceneRender:
        return SceneRender(
            order=scene.order,
            scene_id=scene.scene_id,
            status=RenderStatus.CANCELLED,
            renderer=self.identity(),
            error_code=RenderErrorCode.CANCELLED,
            error_message=message,
        )

    def fonts(self) -> tuple[str, ...]:
        return tuple(sorted(self.inspect_support().available_fonts))

    def cancel(self) -> None:
        """Request cancellation of in-flight work (best effort)."""

        token = self._active_cancel
        if token is not None:
            token.cancel()

    # -- internals shared by implementations ------------------------------------
    def __init__(self, config: Optional[RenderConfig] = None, object_store=None) -> None:
        self.config = config or RenderConfig()
        self.object_store = object_store
        self._active_cancel: Optional[CancelToken] = None
        self._lock = threading.Lock()
        self._in_flight = 0
        self._consecutive_failures = 0
        self._total_rendered = 0
        self._total_failed = 0
        self._last_error: Optional[str] = None

    def identity(self) -> RendererIdentity:
        return RendererIdentity(
            name=self.renderer_id,
            version=self.renderer_version,
            engine=self.engine,
            config_hash=self.config.config_hash(),
            data_region=self.config.data_region,
        )

    def _persist_asset(self, payload: bytes, extension: str) -> str:
        """Content-addressed asset write; identical bytes reuse one key.

        Idempotency (``DOCUMENT_RENDERER.md``): re-rendering the same document
        targets the same key and does not write again.
        """

        key = f"renders/{hashlib.sha256(payload).hexdigest()}.{extension}"
        if self.object_store is None:
            raise RendererError(RenderErrorCode.STORAGE_FAILURE, "no object store configured")
        try:
            if not self.object_store.exists(key):
                self.object_store.put(key, payload)
        except StorageError as exc:
            raise RendererError(RenderErrorCode.STORAGE_FAILURE, str(exc)) from exc
        return key

    #: Fidelity this renderer produces by default; the ADR-pending local
    #: implementation is structural, never native.
    fidelity_ceiling: ClassVar[str] = FIDELITY_STRUCTURAL
    degraded_fidelity: ClassVar[str] = FIDELITY_DEGRADED

    def missing_fonts(self, scene: SlideScene) -> tuple[str, ...]:
        return tuple(f for f in scene.fonts() if f not in self.config.available_fonts)

    def unsupported_kinds(self, scene: SlideScene) -> tuple[str, ...]:
        return tuple(
            sorted({o.kind for o in scene.objects if o.kind not in self.supported_kinds})
        )

    def classify(
        self, *, missing_fonts: tuple[str, ...], unsupported_kinds: tuple[str, ...]
    ) -> str:
        """native -> compatible -> structural -> degraded (``04_CONTENT_COMPILER.md``)."""

        if missing_fonts or unsupported_kinds:
            return self.degraded_fidelity
        return self.fidelity_ceiling

    # -- circuit breaker ---------------------------------------------------------
    def _record_result(self, result: SceneRender) -> None:
        with self._lock:
            if result.status is RenderStatus.FAILED:
                self._total_failed += 1
                self._consecutive_failures += 1
                self._last_error = result.error_message
            elif result.status is RenderStatus.RENDERED:
                self._total_rendered += 1
                self._consecutive_failures = 0

    def trip_if_unhealthy(self) -> bool:
        """Return True when the breaker threshold has been reached."""

        return self._consecutive_failures >= self.config.circuit_failure_threshold

    def circuit_state(self) -> str:
        if self.trip_if_unhealthy():
            return "open"
        if self._consecutive_failures:
            return "half_open"
        return "closed"

    def health(self) -> RendererHealth:
        return RendererHealth(
            state=self.circuit_state(),
            consecutive_failures=self._consecutive_failures,
            last_error=self._last_error,
            total_rendered=self._total_rendered,
            total_failed=self._total_failed,
            in_flight=self._in_flight,
            max_concurrency=1,
        )
