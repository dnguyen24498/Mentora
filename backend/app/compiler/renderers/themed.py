"""Platform-themed renderer: Content IR -> the platform's own slide look (V0-019).

The default render mode. Where ``renderers/structural.py`` reproduces the source
deck's own geometry and styling, this renderer **re-authors** the extracted
content in a theme the platform controls (``renderers/mentora_theme.py``):

* the theme owns the typefaces, so an unavailable source font can never degrade
  the scene — the missing-font failure mode disappears by construction;
* contrast, type scale, and reading order are ours, so accessibility is
  auditable instead of inherited from an arbitrary author's deck;
* every uploaded deck gets one consistent look.

What is preserved is the **content**: every text paragraph, picture, and table
cell in the IR is placed ("re-flow, never re-select"). What is not reproduced is
the source layout — that is the deliberate product decision in ``TASK.md``.

Because the output is a re-authoring, the fidelity gate is re-scoped: the
question is no longer "does it look like the original" but "is the content
complete and does it fit". An unmapped object (chart/SmartArt) or content that
cannot fit degrades the scene (`UNSUPPORTED_OBJECT:`, `TEXT_OVERFLOW:`,
`CONTENT_DROPPED:`) so a teacher reviews it, rather than being silently dropped.

It is still **not** a native PowerPoint render and is never reported as one: the
only inputs are the Content IR and the picture bytes the compiler injects
(``DEC-CONTENT-001``), and ``DEC-TECH-005`` (native rendering) stays OPEN.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import replace
from typing import Mapping, Optional
from xml.sax.saxutils import escape

from app.compiler.imaging import image_size
from app.compiler.models.ir import (
    FIDELITY_DEGRADED,
    FIDELITY_THEMED,
    ContentIRDocument,
    ShapeObject,
    SlideScene,
    TextParagraph,
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
    RendererIdentity,
    SceneRender,
)
from app.compiler.renderers.mentora_theme import DEFAULT_THEME, MentoraTheme
from app.compiler.renderers.structural import (
    MEDIA_BUDGET_PREFIX,
    MEDIA_UNAVAILABLE_PREFIX,
    PT_PER_PIXEL,
    UNSUPPORTED_MEDIA_PREFIX,
    UNSUPPORTED_OBJECT_PREFIX,
    _attr,
    _num,
    _wrap,
)

#: ``CONTENT_DROPPED:<object>#<ref>`` — IR content the renderer failed to place.
#: Must never happen; it is the completeness gate's alarm, not a normal path.
CONTENT_DROPPED_PREFIX = "CONTENT_DROPPED:"
#: ``TEXT_OVERFLOW:<object>#<ref>`` — content was drawn but did not fit the slide.
TEXT_OVERFLOW_PREFIX = "TEXT_OVERFLOW:"

#: Non-text object kinds that cannot be re-authored into the theme. A chart or a
#: SmartArt frame loses information if it is flattened, so it is flagged for
#: review instead of being replaced by a decorative box.
UNREAUTHORABLE_KINDS = frozenset({"chart", "graphicFrame"})

#: Object kinds whose *text* is never rendered as body copy (a table's text lives
#: in its cells; a chart's text is not extracted at all).
_NON_BODY_TEXT_KINDS = frozenset({"table", "chart", "graphicFrame"})

_ANCHORS = {"l": "start", "just": "start", "dist": "start", "ctr": "middle", "r": "end"}


def _basename(part: Optional[str]) -> str:
    return part.rsplit("/", 1)[-1] if part else ""


def _paragraphs_with_text(obj: ShapeObject) -> list[TextParagraph]:
    return [p for p in obj.paragraphs if p.text.strip()]


def _table_grid(obj: ShapeObject) -> list[list[str]]:
    if obj.table:
        return [list(map(str, row)) for row in obj.table]
    if obj.table_cells:
        return [
            [" ".join(p.text for p in cell.paragraphs if p.text).strip() for cell in row]
            for row in obj.table_cells
        ]
    return []


def _cell_paragraphs(obj: ShapeObject, row: int, column: int, fallback: str) -> list[TextParagraph]:
    cells = obj.table_cells or []
    if row < len(cells) and column < len(cells[row]):
        cell = cells[row][column]
        if cell.paragraphs:
            return list(cell.paragraphs)
    return [TextParagraph(level=0, text=fallback)] if fallback else []


def content_refs(scene: SlideScene) -> set[str]:
    """Every addressable content unit of a scene: text, pictures, table cells.

    Decorative geometry (a bare shape, a connector, a layout ruler) carries no
    extractable content and is intentionally re-themed away, so it contributes no
    reference. This is what "content preserved" means precisely.
    """

    refs: set[str] = set()
    for obj in scene.objects:
        for index, paragraph in enumerate(obj.paragraphs):
            if paragraph.text.strip():
                refs.add(f"{obj.source_id}#p{index}")
        if obj.kind == "picture" and obj.media_ref:
            refs.add(f"{obj.source_id}#img")
        if obj.kind == "table":
            for row_index, row in enumerate(_table_grid(obj)):
                for column_index, cell in enumerate(row):
                    if cell.strip():
                        refs.add(f"{obj.source_id}#tc{row_index},{column_index}")
    return refs


# -- block model ------------------------------------------------------------------
class _Block:
    """One content unit of the re-authored flow."""

    __slots__ = ("kind", "obj")

    def __init__(self, kind: str, obj: Optional[ShapeObject] = None) -> None:
        self.kind = kind
        self.obj = obj


def _blocks(scene: SlideScene) -> list[_Block]:
    """Scene objects as an ordered flow of content blocks.

    ``shape``/``connector``/``group`` objects that carry text become text blocks
    (their text is content); those that carry none are decoration and drop out of
    the flow on purpose.
    """

    blocks: list[_Block] = []
    for obj in sorted(scene.objects, key=lambda o: (o.reading_order, o.source_id)):
        if obj.kind in UNREAUTHORABLE_KINDS and not _paragraphs_with_text(obj):
            blocks.append(_Block("unsupported", obj))
            continue
        if obj.kind == "table":
            blocks.append(_Block("table", obj))
            continue
        if _paragraphs_with_text(obj) and obj.kind not in _NON_BODY_TEXT_KINDS:
            blocks.append(_Block("text", obj))
            continue
        if obj.kind == "picture":
            blocks.append(_Block("image", obj))
    return blocks


def _is_title(obj: ShapeObject) -> bool:
    placeholder = (obj.placeholder or "").lower()
    if placeholder in ("title", "ctrtitle"):
        return True
    for paragraph in obj.paragraphs:
        for run in paragraph.runs:
            if run.size_pt and run.size_pt >= 28.0:
                return True
    return False


def _title_block(blocks: list[_Block]) -> Optional[_Block]:
    """The block that becomes the slide heading, or ``None``."""

    for block in blocks:
        if block.kind == "text" and block.obj is not None and _is_title(block.obj):
            return block
    texts = [b for b in blocks if b.kind == "text" and b.obj is not None]
    if len(texts) == 1:
        paragraphs = _paragraphs_with_text(texts[0].obj)  # type: ignore[arg-type]
        if len(paragraphs) == 1 and len(paragraphs[0].text) <= 90:
            return texts[0]
    return None


def classify_scene(scene: SlideScene) -> str:
    """Deterministic archetype of a slide, used to pick its presentation.

    One of ``title``, ``bullets``, ``content``, ``table``, ``media``, ``mixed``,
    ``empty``. Pure function of the IR, so it is stable and unit-testable.
    """

    blocks = _blocks(scene)
    title = _title_block(blocks)
    body = [b for b in blocks if b is not title]
    has_table = any(b.kind == "table" for b in body)
    images = [b for b in body if b.kind == "image"]
    texts = [b for b in body if b.kind == "text"]

    if has_table:
        return "table"
    if images and not texts:
        return "media"
    if images:
        return "mixed"
    if not body and title is not None:
        return "title"
    if not body and title is None:
        return "empty"
    bulleted = any(
        p.bullet or p.level > 0
        for block in texts
        if block.obj is not None
        for p in block.obj.paragraphs
    )
    return "bullets" if bulleted else "content"


class _ThemedCanvas:
    """SVG assembly state for one themed slide."""

    def __init__(
        self,
        width: float,
        height: float,
        scene: SlideScene,
        theme: MentoraTheme,
        media: Mapping[str, bytes],
        config: RenderConfig,
        warnings: list[str],
    ) -> None:
        self.width = width
        self.height = height
        self.scene = scene
        self.theme = theme
        self.media = media
        self.config = config
        self.warnings = warnings
        self.defs: list[str] = []
        self._ids = 0
        self.inlined_bytes = 0
        self.placed: set[str] = set()
        #: Content placed outside the re-measured flow (the heading), which must
        #: survive a flow re-measurement.
        self.committed: set[str] = set()

    def next_id(self, prefix: str) -> str:
        self._ids += 1
        return f"{prefix}{self._ids}"

    def commit(self) -> None:
        """Move current placements out of the re-measurable flow set."""

        self.committed |= self.placed
        self.placed = set()

    def begin_flow(self, warnings_floor: int) -> None:
        """Reset per-attempt state so a re-measured flow is byte-identical.

        The flow can be measured more than once (auto-shrink), so ids, collected
        definitions, the inline-media budget, and any warnings the attempt raised
        must all start clean; otherwise the second measurement would leak
        duplicate ``<defs>`` and duplicated warnings.
        """

        self.defs = []
        self._ids = 0
        self.inlined_bytes = 0
        self.placed = set()
        del self.warnings[warnings_floor:]

    def image_href(self, part: Optional[str]) -> Optional[str]:
        """A ``data:`` URI for a picture part, honouring the inline budget.

        Budget/format problems are *non-degrading* (V0-018 precedent): the picture
        becomes a labelled placeholder and the scene is still complete.
        """

        if not part:
            self.warnings.append(f"{UNSUPPORTED_MEDIA_PREFIX}unresolved")
            return None
        payload = self.media.get(part)
        if payload is None:
            self.warnings.append(f"{MEDIA_UNAVAILABLE_PREFIX}{part}")
            return None
        from app.compiler.media import media_type_for_part

        mime = media_type_for_part(part)
        if mime is None:
            self.warnings.append(f"{UNSUPPORTED_MEDIA_PREFIX}{_basename(part)}")
            return None
        if self.inlined_bytes + len(payload) > self.config.max_inline_media_bytes:
            self.warnings.append(f"{MEDIA_BUDGET_PREFIX}{part}")
            return None
        self.inlined_bytes += len(payload)
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime};base64,{encoded}"


class ThemedSvgRenderer(DocumentRenderer):
    """Re-authors every slide in the platform theme (the default render mode)."""

    renderer_id = "mentora-themed-svg"
    renderer_version = "1.0.0"
    engine = "mentora-theme-svg"
    fidelity_ceiling = FIDELITY_THEMED
    degraded_fidelity = FIDELITY_DEGRADED
    #: A chart/SmartArt frame cannot be re-authored without destroying meaning.
    supported_kinds = ("text", "shape", "picture", "table", "connector", "group")

    def __init__(
        self,
        object_store=None,
        config: Optional[RenderConfig] = None,
        *,
        theme: Optional[MentoraTheme] = None,
    ) -> None:
        super().__init__(config=config, object_store=object_store)
        self.theme = theme or DEFAULT_THEME

    # -- interface --------------------------------------------------------------
    def inspect_support(self) -> CapabilityReport:
        return CapabilityReport(
            supports=True,
            engine=self.engine,
            version=self.renderer_version,
            fidelity_ceiling=self.fidelity_ceiling,
            supported_kinds=self.supported_kinds,
            available_fonts=tuple(sorted(self.theme.available_fonts)),
            reasons=(
                f"themed renderer: content is re-authored in the platform theme "
                f"'{self.theme.name}' v{self.theme.version}; the source deck's own "
                "layout is not reproduced",
                "the theme owns its typefaces, so unavailable source fonts do not "
                "degrade a themed scene",
                "charts and SmartArt cannot be re-authored and require review",
                "native PowerPoint rendering is an OPEN decision (DEC-TECH-005)",
            ),
        )

    def missing_fonts(self, scene: SlideScene) -> tuple[str, ...]:
        """Always empty: the theme owns the typefaces (the source font is moot)."""

        del scene
        return ()

    def identity(self) -> RendererIdentity:
        """Provenance, with the theme folded into the config hash.

        A theme change alters every rendered slide, so it must change the content
        package version. ``RenderConfig`` is theme-agnostic (``base.py``), so the
        theme's canonical form is hashed in here rather than in the shared config.
        """

        base = super().identity()
        payload = json.dumps(
            {"config_hash": base.config_hash, "theme": self.theme.canonical()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return replace(base, config_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest())

    def theme_identity(self) -> dict[str, str]:
        return self.theme.identity()

    # -- per scene --------------------------------------------------------------
    def _attempt_scene(
        self,
        request: RenderRequest,
        scene: SlideScene,
        token: CancelToken,
        budget: RenderBudget,
    ) -> SceneRender:
        started = time.monotonic()
        if token.cancelled:
            return self._cancelled(scene, "render cancelled")
        if budget.expired():
            return self._failed(scene, RenderErrorCode.RENDER_TIMEOUT, "render deadline exceeded")

        unsupported = self.unsupported_kinds(scene)
        warnings: list[str] = [f"{UNSUPPORTED_OBJECT_PREFIX}{kind}" for kind in unsupported]

        try:
            payload, dropped, overflow = self._svg(request.document, scene, request.media, warnings)
            if len(payload) > self.config.max_asset_bytes:
                raise RendererError(
                    RenderErrorCode.OUTPUT_TOO_LARGE,
                    f"rendered asset is {len(payload)} bytes > {self.config.max_asset_bytes}",
                )
            asset_ref = self._persist_asset(payload, "svg")
        except RendererError as exc:
            return self._failed(scene, exc.code, exc.message)
        except Exception as exc:  # defensive: a bad scene must not sink the deck
            return self._failed(
                scene, RenderErrorCode.RENDER_FAILED, f"{type(exc).__name__}: {exc}"
            )

        if budget.expired():
            return self._failed(scene, RenderErrorCode.RENDER_TIMEOUT, "render deadline exceeded")

        for ref in sorted(dropped):
            warnings.append(f"{CONTENT_DROPPED_PREFIX}{ref}")
        if overflow:
            warnings.append(f"{TEXT_OVERFLOW_PREFIX}{scene.scene_id}")

        degraded = bool(dropped) or overflow or bool(unsupported)
        if degraded:
            warnings.append("fidelity degraded; meaning requires review")

        return SceneRender(
            order=scene.order,
            scene_id=scene.scene_id,
            status=RenderStatus.RENDERED,
            fidelity=FIDELITY_DEGRADED if degraded else FIDELITY_THEMED,
            asset_ref=asset_ref,
            asset_bytes=len(payload),
            renderer=request.identity,
            fonts_used=(),
            missing_fonts=(),
            warnings=tuple(warnings),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    # -- SVG --------------------------------------------------------------------
    def _svg(
        self,
        document: ContentIRDocument,
        scene: SlideScene,
        media: Mapping[str, bytes],
        warnings: list[str],
    ) -> tuple[bytes, set[str], bool]:
        del document
        width, height = float(self.config.width_px), float(self.config.height_px)
        canvas = _ThemedCanvas(width, height, scene, self.theme, media, self.config, warnings)

        theme = self.theme
        left = theme.margin_px
        content_w = max(80.0, width - 2 * left)
        top = theme.margin_px
        footer_line = height - 56.0
        content_bottom = footer_line - 22.0

        blocks = _blocks(scene)
        title = _title_block(blocks)
        body = [b for b in blocks if b is not title]
        archetype = classify_scene(scene)

        parts: list[str] = [
            f'<rect x="0" y="0" width="{_num(width)}" height="{_num(height)}" '
            f'fill="{_attr(theme.background)}"/>',
            f'<rect x="0" y="0" width="{_num(width)}" height="{_num(theme.accent_bar_px)}" '
            f'fill="{_attr(theme.primary)}"/>',
        ]

        cursor = top
        if title is not None and title.obj is not None:
            # A title-only slide is a *hero*: a larger heading, vertically centred.
            hero = archetype == "title"
            title_parts, title_bottom = self._title(
                canvas, title.obj, left, top, content_w, hero=hero
            )
            if hero:
                offset = max(0.0, (content_bottom - top - (title_bottom - top)) / 2.0)
                if offset > 1.0:
                    title_parts, title_bottom = self._title(
                        canvas, title.obj, left, top + offset, content_w, hero=hero
                    )
            parts.extend(title_parts)
            cursor = title_bottom + theme.gutter_px
        # The heading's content is placed; the flow below is measured (and possibly
        # re-measured at a smaller scale) from a clean slate, so commit it first.
        canvas.commit()

        body_top = cursor
        available = max(40.0, content_bottom - body_top)

        warnings_floor = len(warnings)
        scale = 1.0
        while True:
            canvas.begin_flow(warnings_floor)
            flow, flow_height, _placed = self._flow(
                canvas, body, left, body_top, content_w, scale, available
            )
            if flow_height <= available or scale <= theme.min_scale + 0.001:
                break
            # Shrink toward the readable floor, then re-measure. Never drop text
            # silently: at the floor a remaining overflow is reported instead.
            scale = max(theme.min_scale, scale * max(0.7, (available / flow_height) * 0.97))
        overflow = flow_height > available

        if overflow:
            clip_id = canvas.next_id("bodyclip")
            canvas.defs.append(
                f'<clipPath id="{clip_id}"><rect x="0" y="{_num(0)}" width="{_num(width)}" '
                f'height="{_num(content_bottom)}"/></clipPath>'
            )
            parts.append(f'<g clip-path="url(#{clip_id})">')
        parts.extend(flow)
        if overflow:
            parts.append("</g>")

        parts.append(self._footer(canvas, scene.order))

        dropped = content_refs(scene) - canvas.placed - canvas.committed
        defs = "".join(canvas.defs)
        head = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(width)}" '
            f'height="{_num(height)}" viewBox="0 0 {_num(width)} {_num(height)}" role="img">',
            f"<title>{escape(scene.scene_id)}</title>",
            f"<defs>{defs}</defs>" if defs else "",
        ]
        payload = "".join(part for part in [*head, *parts, "</svg>"] if part).encode("utf-8")
        return payload, dropped, overflow

    # -- title ------------------------------------------------------------------
    def _title(
        self,
        canvas: _ThemedCanvas,
        obj: ShapeObject,
        x: float,
        y: float,
        width: float,
        *,
        hero: bool = False,
    ) -> tuple[list[str], float]:
        theme = self.theme
        paragraphs = _paragraphs_with_text(obj)
        size_pt = theme.title_pt * (1.18 if hero else 1.0)
        probe = self._measure_paragraphs(paragraphs, size_pt, width, title=True)
        if probe > 2:
            size_pt = theme.heading_pt
        parts: list[str] = []
        cursor = y
        first = True
        for paragraph_index, paragraph in enumerate(obj.paragraphs):
            if not paragraph.text.strip():
                continue
            size_px = size_pt / PT_PER_PIXEL
            family = theme.heading_stack
            bold = first or any(run.bold for run in paragraph.runs)
            color = theme.ink if first else theme.muted
            lines = _wrap(paragraph.text, size_px, width, bold)
            line_height = size_px * 1.18
            for line in lines:
                baseline = cursor + size_px * 0.84
                attributes = [
                    f'x="{_num(x)}"',
                    f'y="{_num(baseline)}"',
                    f'font-family="{_attr(family)}"',
                    f'font-size="{_num(size_px)}"',
                    f'fill="{_attr(color)}"',
                ]
                if bold:
                    attributes.append('font-weight="bold"')
                parts.append(
                    f'<text {" ".join(attributes)} xml:space="preserve">{escape(line)}</text>'
                )
                cursor += line_height
            cursor += 4.0
            canvas.placed.add(f"{obj.source_id}#p{paragraph_index}")
            first = False
        cursor += 6.0
        parts.append(
            f'<rect x="{_num(x)}" y="{_num(cursor)}" width="{_num(min(width, 132.0))}" '
            f'height="4" rx="2" fill="{_attr(theme.accent)}"/>'
        )
        return parts, cursor + 4.0

    @staticmethod
    def _measure_paragraphs(
        paragraphs: list[TextParagraph], size_pt: float, width: float, *, title: bool
    ) -> int:
        size_px = size_pt / PT_PER_PIXEL
        return sum(
            len(_wrap(p.text, size_px, width, title)) for p in paragraphs if p.text.strip()
        )

    # -- body flow --------------------------------------------------------------
    def _flow(
        self,
        canvas: _ThemedCanvas,
        blocks: list[_Block],
        x: float,
        y: float,
        width: float,
        scale: float,
        max_height: float,
    ) -> tuple[list[str], float, set[str]]:
        theme = self.theme
        parts: list[str] = []
        cursor = y
        index = 0
        while index < len(blocks):
            block = blocks[index]
            assert block.obj is not None
            if block.kind == "text":
                text_parts, cursor = self._text_block(canvas, block.obj, x, cursor, width, scale)
                parts.extend(text_parts)
                cursor += theme.gutter_px * 0.6
                index += 1
            elif block.kind == "image":
                group: list[_Block] = []
                while index < len(blocks) and blocks[index].kind == "image":
                    group.append(blocks[index])
                    index += 1
                image_parts, cursor = self._image_row(
                    canvas, group, x, cursor, width, scale, max_height
                )
                parts.extend(image_parts)
                cursor += theme.gutter_px * 0.6
            elif block.kind == "table":
                table_parts, cursor = self._table(canvas, block.obj, x, cursor, width, scale)
                parts.extend(table_parts)
                cursor += theme.gutter_px * 0.6
                index += 1
            else:  # unsupported
                parts.extend(self._unsupported(canvas, block.obj, x, cursor, width, scale))
                cursor += 96.0 * scale + theme.gutter_px * 0.6
                index += 1
        return parts, cursor - y, canvas.placed

    def _text_block(
        self,
        canvas: _ThemedCanvas,
        obj: ShapeObject,
        x: float,
        y: float,
        width: float,
        scale: float,
    ) -> tuple[list[str], float]:
        theme = self.theme
        parts: list[str] = []
        cursor = y
        for paragraph_index, paragraph in enumerate(obj.paragraphs):
            if not paragraph.text.strip():
                continue
            level = max(0, paragraph.level)
            size_pt = max(theme.caption_pt, theme.body_pt * (0.92**level))
            size_px = (size_pt / PT_PER_PIXEL) * scale
            bold = any(run.bold for run in paragraph.runs)
            italic = any(run.italic for run in paragraph.runs)
            bullet = self._bullet(paragraph)
            indent = 18.0 * level + (22.0 if bullet else 0.0) * scale
            anchor = _ANCHORS.get(paragraph.align or "l", "start")
            text_x = x + indent
            if anchor == "middle":
                text_x = x + width / 2
            elif anchor == "end":
                text_x = x + width
            lines = _wrap(paragraph.text, size_px, max(20.0, width - indent), bold)
            line_height = size_px * 1.42
            for line_index, line in enumerate(lines):
                baseline = cursor + size_px * 0.82
                if bullet and line_index == 0:
                    parts.append(
                        f'<circle cx="{_num(x + 8.0 * scale)}" cy="{_num(cursor + size_px * 0.44)}" '
                        f'r="{_num(max(2.0, size_px * 0.13))}" fill="{_attr(theme.accent)}"/>'
                    )
                attributes = [
                    f'x="{_num(text_x)}"',
                    f'y="{_num(baseline)}"',
                    f'font-family="{_attr(theme.font_stack)}"',
                    f'font-size="{_num(size_px)}"',
                    f'fill="{_attr(theme.ink)}"',
                ]
                if bold:
                    attributes.append('font-weight="bold"')
                if italic:
                    attributes.append('font-style="italic"')
                if anchor != "start":
                    attributes.append(f'text-anchor="{anchor}"')
                parts.append(
                    f'<text {" ".join(attributes)} xml:space="preserve">{escape(line)}</text>'
                )
                cursor += line_height
            cursor += 7.0 * scale
            canvas.placed.add(f"{obj.source_id}#p{paragraph_index}")
        return parts, cursor - y

    @staticmethod
    def _bullet(paragraph: TextParagraph) -> bool:
        bullet = paragraph.bullet or {}
        if bullet.get("none"):
            return False
        return bool(bullet) or paragraph.level > 0

    def _image_row(
        self,
        canvas: _ThemedCanvas,
        group: list[_Block],
        x: float,
        y: float,
        width: float,
        scale: float,
        max_height: float,
    ) -> tuple[list[str], float]:
        theme = self.theme
        columns = 2 if len(group) > 1 else 1
        gutter = theme.gutter_px
        cell_w = (width - gutter * (columns - 1)) / columns
        parts: list[str] = []
        cursor = y
        for start in range(0, len(group), columns):
            row = group[start : start + columns]
            remaining = max(48.0, max_height - (cursor - y))
            frames: list[tuple[ShapeObject, float, float]] = []
            for offset, block in enumerate(row):
                assert block.obj is not None
                aspect = self._aspect(canvas, block.obj)
                # Fit within the cell *and* the remaining space, keeping the
                # picture's own aspect ratio: a frame is never distorted, and a
                # picture on its own can never overflow the slide.
                frame_h = min(cell_w / aspect, remaining, cell_w * 1.1)
                frame_w = frame_h * aspect
                frames.append((block.obj, frame_w, frame_h))
            row_h = max(frame_h for _obj, _w, frame_h in frames)
            for offset, (obj, frame_w, frame_h) in enumerate(frames):
                cell_x = x + offset * (cell_w + gutter)
                parts.append(
                    self._image(
                        canvas,
                        obj,
                        cell_x + (cell_w - frame_w) / 2.0,
                        cursor + (row_h - frame_h) / 2.0,
                        frame_w,
                        frame_h,
                    )
                )
                canvas.placed.add(f"{obj.source_id}#img")
            cursor += row_h + gutter * 0.7
        return parts, cursor - y

    @staticmethod
    def _aspect(canvas: _ThemedCanvas, obj: ShapeObject) -> float:
        """Width/height of a picture, read from its bytes where possible."""

        payload = canvas.media.get(obj.media_ref or "")
        if payload:
            size = image_size(payload)
            if size and size[0] > 0 and size[1] > 0:
                return size[0] / size[1]
        if obj.bounds and obj.bounds.width and obj.bounds.height:
            return float(obj.bounds.width) / float(obj.bounds.height)
        return 1.6

    def _image(
        self,
        canvas: _ThemedCanvas,
        obj: ShapeObject,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> str:
        theme = self.theme
        href = canvas.image_href(obj.media_ref) if obj.media_type else None
        radius = theme.radius_px
        if href is None:
            label = _basename(obj.media_ref) or obj.name or "image"
            return (
                f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" '
                f'rx="{_num(radius)}" fill="{_attr(theme.surface)}" '
                f'stroke="{_attr(theme.border)}" stroke-dasharray="5 4"/>'
                f'<text x="{_num(x + width / 2)}" y="{_num(y + height / 2)}" text-anchor="middle" '
                f'font-family="{_attr(theme.font_stack)}" font-size="{_num(theme.caption_pt / PT_PER_PIXEL)}" '
                f'fill="{_attr(theme.muted)}">{escape(label)}</text>'
            )
        clip_id = canvas.next_id("imgclip")
        canvas.defs.append(
            f'<clipPath id="{clip_id}"><rect x="{_num(x)}" y="{_num(y)}" '
            f'width="{_num(width)}" height="{_num(height)}" rx="{_num(radius)}"/></clipPath>'
        )
        return (
            f'<g clip-path="url(#{clip_id})">'
            f'<image x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" '
            f'preserveAspectRatio="xMidYMid slice" href="{_attr(href)}"/>'
            f"</g>"
        )

    def _table(
        self,
        canvas: _ThemedCanvas,
        obj: ShapeObject,
        x: float,
        y: float,
        width: float,
        scale: float,
    ) -> tuple[list[str], float]:
        theme = self.theme
        rows = _table_grid(obj)
        if not rows:
            return [], 0.0
        columns = max(len(row) for row in rows)
        column_widths = self._column_widths(obj, columns, width)
        font_px = max(8.0, (theme.caption_pt / PT_PER_PIXEL) * scale)
        row_h = _clamp(34.0 * scale, 20.0, 44.0)
        heights = [row_h] * len(rows)
        heights[0] = row_h + 4.0

        parts: list[str] = []
        cursor = y
        for row_index, row in enumerate(rows):
            column_x = x
            fill = self._row_fill(row_index)
            parts.append(
                f'<rect x="{_num(x)}" y="{_num(cursor)}" width="{_num(width)}" '
                f'height="{_num(heights[row_index])}" {fill}/>'
            )
            for column_index, cell_text in enumerate(row):
                column_w = column_widths[column_index] if column_index < len(column_widths) else width / columns
                if row_index == 0:
                    parts.append(
                        f'<rect x="{_num(column_x)}" y="{_num(cursor)}" '
                        f'width="{_num(column_w)}" height="{_num(heights[row_index])}" '
                        f'fill="{_attr(theme.primary)}"/>'
                    )
                anchor = "middle" if row_index == 0 else "start"
                text_x = column_x + column_w / 2 if row_index == 0 else column_x + 10.0
                color = theme.primary_ink if row_index == 0 else theme.ink
                paragraphs = _cell_paragraphs(obj, row_index, column_index, cell_text)
                text = " ".join(p.text for p in paragraphs if p.text).strip()
                if text:
                    max_width = max(20.0, column_w - (20.0 if row_index == 0 else 16.0))
                    lines = _wrap(text, font_px, max_width, row_index == 0)[:2]
                    line_height = font_px * 1.3
                    block_h = line_height * len(lines)
                    line_y = cursor + (heights[row_index] - block_h) / 2
                    for line in lines:
                        baseline = line_y + font_px * 0.84
                        attributes = [
                            f'x="{_num(text_x)}"',
                            f'y="{_num(baseline)}"',
                            f'font-family="{_attr(theme.font_stack)}"',
                            f'font-size="{_num(font_px)}"',
                            f'fill="{_attr(color)}"',
                        ]
                        if row_index == 0:
                            attributes.append('font-weight="bold"')
                            attributes.append('text-anchor="middle"')
                        parts.append(
                            f'<text {" ".join(attributes)} xml:space="preserve">{escape(line)}</text>'
                        )
                        line_y += line_height
                    canvas.placed.add(f"{obj.source_id}#tc{row_index},{column_index}")
            cursor += heights[row_index]
        parts.append(
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" '
            f'height="{_num(cursor - y)}" fill="none" stroke="{_attr(theme.border)}"/>'
        )
        return parts, cursor - y

    def _row_fill(self, row_index: int) -> str:
        theme = self.theme
        if row_index == 0:
            return f'fill="{_attr(theme.primary)}"'
        return f'fill="{_attr(theme.surface if row_index % 2 else theme.background)}"'

    @staticmethod
    def _column_widths(obj: ShapeObject, columns: int, width: float) -> list[float]:
        values = obj.table_columns or []
        if len(values) < columns:
            return [width / max(1, columns)] * max(1, columns)
        total = sum(values)
        if total <= 0:
            return [width / max(1, columns)] * max(1, columns)
        return [width * value / total for value in values[:columns]]

    def _unsupported(
        self,
        canvas: _ThemedCanvas,
        obj: ShapeObject,
        x: float,
        y: float,
        width: float,
        scale: float,
    ) -> list[str]:
        theme = self.theme
        height = 96.0 * scale
        label = f"{obj.kind} not re-authored: {obj.name or _basename(obj.media_ref)}"
        return [
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" '
            f'rx="{_num(theme.radius_px)}" fill="{_attr(theme.surface)}" '
            f'stroke="{_attr(theme.primary)}" stroke-dasharray="6 4"/>',
            f'<text x="{_num(x + width / 2)}" y="{_num(y + height / 2)}" text-anchor="middle" '
            f'font-family="{_attr(theme.font_stack)}" '
            f'font-size="{_num((theme.caption_pt / PT_PER_PIXEL) * scale)}" '
            f'fill="{_attr(theme.primary)}">{escape(label)}</text>',
        ]

    def _footer(self, canvas: _ThemedCanvas, order: int) -> str:
        theme = self.theme
        width, height = canvas.width, canvas.height
        line_y = height - 56.0
        baseline = height - 30.0
        return (
            f'<line x1="{_num(theme.margin_px)}" y1="{_num(line_y)}" '
            f'x2="{_num(width - theme.margin_px)}" y2="{_num(line_y)}" '
            f'stroke="{_attr(theme.border)}"/>'
            f'<text x="{_num(theme.margin_px)}" y="{_num(baseline)}" '
            f'font-family="{_attr(theme.font_stack)}" '
            f'font-size="{_num(theme.footer_pt / PT_PER_PIXEL)}" '
            f'fill="{_attr(theme.muted)}">{escape(theme.footer_label)}</text>'
            f'<text x="{_num(width - theme.margin_px)}" y="{_num(baseline)}" text-anchor="end" '
            f'font-family="{_attr(theme.font_stack)}" '
            f'font-size="{_num(theme.footer_pt / PT_PER_PIXEL)}" '
            f'fill="{_attr(theme.muted)}">{order + 1}</text>'
        )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


__all__ = [
    "CONTENT_DROPPED_PREFIX",
    "ThemedSvgRenderer",
    "TEXT_OVERFLOW_PREFIX",
    "UNREAUTHORABLE_KINDS",
    "classify_scene",
    "content_refs",
]
