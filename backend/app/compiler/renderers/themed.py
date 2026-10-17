"""Platform-themed renderer (V0-019): the content, re-laid out in the theme.

This is the default render mode. It reads the extracted **content** — the text,
tables and pictures of a slide, in reading order — and rebuilds the slide in the
platform's own layout and look:

* ``renderers/flow.py`` lays the content out as **one readable column**: a hoisted
  heading, then the body blocks top-to-bottom, fitted by a type-scale ladder.
* ``renderers/mentora_theme.py`` owns the typeface, the palette and the chrome.
* This module is the bridge: it turns a scene into flow blocks, draws the flow's
  geometry as SVG, and applies the fidelity gate.

Why the author's layout is *not* reproduced
-------------------------------------------
V0-019 first copied the author's geometry and restyled it. On real, art-directed
decks that is what makes slides unreadable: source text frames overlap each other,
sit outside the safe area, or hold more text than they can show, and copying that
onto a different typeface reproduces the problem instead of fixing it. The
platform therefore imposes its *own* grid. The trade-off is explicit and is the
product decision: **placement is the platform's, content is the author's.**

Consequences
------------
* **The font problem disappears.** The theme owns its typefaces, so
  ``missing_fonts()`` is empty by construction: an unavailable source font can no
  longer degrade a themed scene.
* **Overlap is structurally impossible.** The flow places blocks on a cursor
  (:mod:`app.compiler.renderers.flow`), and the platform's page number sits in a
  strip the flow may not enter — so the chrome can never cover content either.
* **Completeness is the gate.** Nothing is dropped: text keeps its paragraphs,
  emphasis, lists and tables, and a picture that cannot be drawn becomes a
  labelled panel with a warning rather than a blank. Content that does not fit
  even at ``theme.min_scale`` is *flagged* for review (``TEXT_OVERFLOW:``) instead
  of being silently truncated.
* **Degradation is explicit.** A chart/SmartArt frame cannot be redrawn from the
  IR, so it becomes a labelled panel and pulls the scene into review.

It is still **not** a native PowerPoint render and is never reported as one
(``DEC-CONTENT-006``): the only inputs are the Content IR and the picture bytes
the compiler injects (``DEC-CONTENT-001``), and ``DEC-TECH-005`` (native
rendering) stays OPEN.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from typing import Mapping, Optional
from xml.sax.saxutils import escape

from app.compiler.imaging import image_size
from app.compiler.models.ir import (
    FIDELITY_DEGRADED,
    FIDELITY_THEMED,
    ShapeObject,
    SlideScene,
    TextParagraph,
)
from app.compiler.renderers import flow
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
# ``_Canvas``/``_attr``/``_num`` are the V0-018 SVG assembly and media-inlining
# helpers (data: URIs, per-scene byte budget, media warnings). Themed mode *wants*
# the same media semantics as faithful mode — a picture that cannot be inlined must
# warn identically — so it shares them rather than re-implementing them.
from app.compiler.renderers.structural import (
    UNSUPPORTED_OBJECT_PREFIX,
    _Canvas,
    _attr,
    _num,
)

#: ``TEXT_OVERFLOW:<scene>`` — the slide's content does not fit the page even at
#: the smallest readable type scale. Everything is still drawn; the scene degrades
#: so a teacher reviews the slide, and the platform's page number is left off so it
#: cannot cover the content.
TEXT_OVERFLOW_PREFIX = "TEXT_OVERFLOW:"

#: Slide-level placeholders that are *deck chrome*, not content: the theme draws
#: its own page number, so these are dropped rather than stacked into the body.
_CHROME_PLACEHOLDERS = frozenset({"ftr", "dt", "sldNum", "sldImg", "hdr"})

#: Object kinds the platform cannot redraw from the IR (``DEC-TECH-005`` OPEN).
_PANEL_KINDS = ("chart", "graphicFrame")

#: Placeholders that name the heading of the slide.
_TITLE_PLACEHOLDERS = ("title", "ctrTitle")

#: Marker per list level, for a block that reads as a list but whose source never
#: resolved a bullet (the extractor resolves only what the cascade actually set).
_LIST_MARKERS = ("\u2022", "\u2013", "\u00b7")

#: Bullet characters safe to draw with the theme's font. A source bullet often
#: comes from Wingdings/Symbol and would render as tofu, so anything else becomes
#: the theme's own marker.
_SAFE_MARKERS = frozenset("\u2022\u2023\u00b7\u25e6\u25aa\u25ab\u2013\u2014-*+>\u00a7")


def _basename(part: Optional[str]) -> str:
    return part.rsplit("/", 1)[-1] if part else ""


def _nominal_size(entries: list["_Entry"]) -> float:
    """The slide's nominal body size: its most common source size.

    Emphasis is *relative to the slide*, not to an absolute point size: a 14 pt
    deck and a 28 pt deck both get the same three rows, and a slide written with
    one size everywhere gets one flat row.
    """

    counts: dict[float, int] = {}
    for entry in entries:
        if entry.kind == "text" and entry.size > 0:
            key = round(entry.size, 2)
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return 0.0
    # Most frequent wins. On a tie the median is the body: with sizes written once
    # each (12/18/40 pt), the middle one is the body and the extremes are the
    # caption and the lead, which is what such a slide means.
    best = max(counts.values())
    tied = sorted(size for size, count in counts.items() if count == best)
    return tied[len(tied) // 2]


def _emphasis(size: float, base: float) -> str:
    """Which theme row a source block belongs to: lead, body, or caption."""

    if base <= 0.0 or size <= 0.0:
        return "body"
    if size >= 1.5 * base:
        return "lead"
    if size <= 0.85 * base:
        return "caption"
    return "body"


def _bullet_marker(paragraph: TextParagraph, *, listed: bool) -> Optional[str]:
    bullet = paragraph.bullet or {}
    if bullet:
        if bullet.get("none"):
            return None
        character = str(bullet.get("char") or "")
        if character:
            return character if character in _SAFE_MARKERS else _LIST_MARKERS[0]
        if bullet.get("autonum"):
            # The IR carries the numbering scheme, not the rendered number; a dot
            # is honest (the theme does not invent an ordinal).
            return _LIST_MARKERS[0]
    if not listed:
        return None
    level = max(0, int(paragraph.level or 0))
    return _LIST_MARKERS[min(level, len(_LIST_MARKERS) - 1)]


def _table_data(obj: ShapeObject) -> tuple[tuple[tuple[str, ...], ...], tuple[float, ...]]:
    """A table's visible grid: empty rows/columns dropped, source widths kept."""

    raw = [[str(cell or "") for cell in row] for row in (obj.table or [])]
    rows = [row for row in raw if any(cell.strip() for cell in row)]
    if not rows:
        return (), ()
    columns = max(len(row) for row in rows)
    keep = [
        index
        for index in range(columns)
        if any(index < len(row) and row[index].strip() for row in rows)
    ]
    if not keep:
        return (), ()
    trimmed = tuple(
        tuple(row[index] if index < len(row) else "" for index in keep) for row in rows
    )
    source = list(obj.table_columns or [])
    if len(source) == columns and sum(source) > 0:
        return trimmed, tuple(float(source[index]) for index in keep)
    return trimmed, ()


@dataclass(frozen=True)
class _Entry:
    """One content-bearing object, with the flow content it produces."""

    kind: str  # text | table | picture | panel
    obj: ShapeObject
    paragraphs: tuple[flow.Paragraph, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    weights: tuple[float, ...] = ()
    image: Optional[flow.Picture] = None
    size: float = 0.0
    text: str = ""


class ThemedSvgRenderer(DocumentRenderer):
    """Draws the extracted content as a platform-styled SVG (the default mode)."""

    renderer_id = "mentora-themed-svg"
    renderer_version = "3.0.0"
    engine = "mentora-theme-svg"
    fidelity_ceiling = FIDELITY_THEMED
    degraded_fidelity = FIDELITY_DEGRADED
    #: A chart/SmartArt frame cannot be redrawn from the IR, so those kinds stay
    #: unsupported and pull the scene into review.
    supported_kinds = ("text", "shape", "picture", "table", "connector", "group")

    def __init__(
        self,
        object_store=None,
        config: Optional[RenderConfig] = None,
        *,
        theme: Optional[MentoraTheme] = None,
    ) -> None:
        super().__init__(object_store=object_store, config=config)
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
                "themed renderer: the extracted content is re-laid out as one "
                f"readable column and styled in the platform theme "
                f"'{self.theme.name}' v{self.theme.version}",
                "the theme owns its typefaces, so unavailable source fonts do not "
                "degrade a themed scene",
                "placement is the platform's and content is the author's: the "
                "source slide's own geometry is not reproduced",
                "charts and SmartArt cannot be redrawn from the IR and require review",
                "native PowerPoint rendering is an OPEN decision (DEC-TECH-005)",
            ),
        )

    def missing_fonts(self, scene: SlideScene) -> tuple[str, ...]:
        """Always empty: the theme owns the typefaces, so the source font is moot."""

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
        return replace(
            base, config_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest()
        )

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
            payload = self._svg(request.document, scene, request.media, warnings)
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
            # The work is done but the end-to-end deadline was blown; the asset is
            # kept (content-addressed and reusable) and the scene is a retryable
            # timeout, exactly as in the faithful mode.
            return self._failed(scene, RenderErrorCode.RENDER_TIMEOUT, "render deadline exceeded")

        degraded = bool(unsupported) or any(
            warning.startswith(TEXT_OVERFLOW_PREFIX) for warning in warnings
        )
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
            fonts_used=tuple(sorted(self.fonts())),
            missing_fonts=(),
            warnings=tuple(warnings),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    # -- SVG --------------------------------------------------------------------
    def _svg(
        self,
        document,
        scene: SlideScene,
        media: Mapping[str, bytes],
        warnings: list[str],
    ) -> bytes:
        del document
        theme = self.theme
        width, height = float(self.config.width_px), float(self.config.height_px)
        canvas = _Canvas(width, height, scene, media, self.config, warnings)

        header, blocks = self._content(scene, media)
        result = flow.layout(blocks=blocks, header=header, theme=theme, width=width, height=height)
        if result.overflow:
            warnings.append(f"{TEXT_OVERFLOW_PREFIX}{scene.scene_id}")

        body: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(width)}" '
            f'height="{_num(height)}" viewBox="0 0 {_num(width)} {_num(height)}" role="img">',
            f"<title>{escape(scene.scene_id)}</title>",
            f'<rect x="0" y="0" width="{_num(width)}" height="{_num(height)}" '
            f'fill="{_attr(theme.background)}"/>',
        ]
        for item in result.items:
            body.append(self._draw(canvas, item))
        if not result.overflow:
            body.append(self._page_number(scene, width, height))

        defs = "".join(canvas.defs)
        parts = [body[0], body[1], f"<defs>{defs}</defs>" if defs else "", *body[2:], "</svg>"]
        return "".join(part for part in parts if part).encode("utf-8")

    def _draw(self, canvas: _Canvas, item: flow.Placed) -> str:
        if isinstance(item, flow.PlacedText):
            return self._draw_text(item)
        if isinstance(item, flow.PlacedRule):
            return self._draw_rule(item)
        if isinstance(item, flow.PlacedTable):
            return self._draw_table(item)
        if isinstance(item, flow.PlacedPicture):
            return self._draw_picture(canvas, item)
        return self._draw_panel(item)

    def _role_ink(self, role: str) -> str:
        theme = self.theme
        if role == "title":
            return theme.primary
        if role in ("kicker", "subtitle", "caption"):
            return theme.muted
        return theme.ink

    def _draw_text(self, item: flow.PlacedText) -> str:
        ink = self._role_ink(item.role)
        parts: list[str] = []
        for line in item.lines:
            if line.marker:
                parts.append(
                    f'<text x="{_num(line.marker_x)}" y="{_num(line.baseline)}" '
                    f'font-family="{_attr(self.theme.font_stack)}" '
                    f'font-size="{_num(line.size)}" fill="{_attr(self.theme.accent)}" '
                    f'xml:space="preserve">{escape(line.marker)}</text>'
                )
            if line.text:
                parts.append(self._line_element(line, ink))
        return "".join(parts)

    def _line_element(self, line: flow.TextLine, ink: str) -> str:
        all_bold = bool(line.spans) and all(span.bold for span in line.spans)
        all_italic = bool(line.spans) and all(span.italic for span in line.spans)
        attributes = [
            f'x="{_num(line.x)}"',
            f'y="{_num(line.baseline)}"',
            f'font-family="{_attr(self.theme.font_stack)}"',
            f'font-size="{_num(line.size)}"',
            f'fill="{_attr(ink)}"',
        ]
        if all_bold:
            attributes.append('font-weight="bold"')
        if all_italic:
            attributes.append('font-style="italic"')
        if line.anchor != "start":
            attributes.append(f'text-anchor="{line.anchor}"')
        if len(line.spans) <= 1:
            content = escape(line.spans[0].text) if line.spans else ""
        else:
            content = "".join(
                self._span_markup(span, all_bold, all_italic) for span in line.spans
            )
        return f'<text {" ".join(attributes)} xml:space="preserve">{content}</text>'

    def _span_markup(self, span: flow.Span, all_bold: bool, all_italic: bool) -> str:
        content = escape(span.text)
        attributes = []
        if span.bold and not all_bold:
            attributes.append('font-weight="bold"')
        if span.italic and not all_italic:
            attributes.append('font-style="italic"')
        return f"<tspan {' '.join(attributes)}>{content}</tspan>" if attributes else content

    def _draw_rule(self, item: flow.PlacedRule) -> str:
        box = item.box
        return (
            f'<line x1="{_num(box.x)}" y1="{_num(box.y)}" x2="{_num(box.right)}" '
            f'y2="{_num(box.y)}" stroke="{_attr(self.theme.border)}" stroke-width="1"/>'
        )

    def _draw_table(self, item: flow.PlacedTable) -> str:
        theme = self.theme
        parts: list[str] = []
        for cell in item.cells:
            fill = theme.surface_alt if cell.header else theme.surface if cell.band else None
            if fill is None:
                continue
            box = cell.box
            parts.append(
                f'<rect x="{_num(box.x)}" y="{_num(box.y)}" width="{_num(box.width)}" '
                f'height="{_num(box.height)}" fill="{_attr(fill)}"/>'
            )
        for cell in item.cells:
            for line in cell.lines:
                if line.text:
                    parts.append(self._line_element(line, theme.ink))
        return "".join(parts)

    def _draw_picture(self, canvas: _Canvas, item: flow.PlacedPicture) -> str:
        image = item.image
        box = item.box
        href = canvas.image_href(image.media_ref)
        if href is None:
            return self._panel(box, image.label)
        left, top, right, bottom = image.crop
        if left or top or right or bottom:
            # ``a:srcRect``: the kept window is scaled to fill the frame and clipped
            # to it (image coordinates, so the frame must not be aspect-fitted).
            keep_w = max(0.01, 1.0 - left - right)
            keep_h = max(0.01, 1.0 - top - bottom)
            full_w, full_h = box.width / keep_w, box.height / keep_h
            clip_id = canvas.next_id("clip")
            canvas.defs.append(
                f'<clipPath id="{clip_id}"><rect x="{_num(box.x)}" y="{_num(box.y)}" '
                f'width="{_num(box.width)}" height="{_num(box.height)}"/></clipPath>'
            )
            return (
                f'<image x="{_num(box.x - left * full_w)}" y="{_num(box.y - top * full_h)}" '
                f'width="{_num(full_w)}" height="{_num(full_h)}" preserveAspectRatio="none" '
                f'href="{_attr(href)}" clip-path="url(#{clip_id})"/>'
            )
        return (
            f'<image x="{_num(box.x)}" y="{_num(box.y)}" width="{_num(box.width)}" '
            f'height="{_num(box.height)}" preserveAspectRatio="xMidYMid meet" '
            f'href="{_attr(href)}"/>'
        )

    def _draw_panel(self, item: flow.PlacedPanel) -> str:
        return self._panel(item.box, item.label)

    def _panel(self, box: flow.Box, label: str) -> str:
        theme = self.theme
        scale = box.height / theme.panel_px if theme.panel_px else 1.0
        size = max(9.0, theme.panel_label_px * min(1.0, scale))
        return (
            f'<rect x="{_num(box.x)}" y="{_num(box.y)}" width="{_num(box.width)}" '
            f'height="{_num(box.height)}" rx="8" fill="{_attr(theme.surface)}" '
            f'stroke="{_attr(theme.border)}" stroke-width="1"/>'
            f'<text x="{_num(box.x + box.width / 2)}" y="{_num(box.y + box.height / 2 + size / 3)}" '
            f'text-anchor="middle" font-family="{_attr(theme.font_stack)}" '
            f'font-size="{_num(size)}" fill="{_attr(theme.muted)}">{escape(label)}</text>'
        )

    def _page_number(self, scene: SlideScene, width: float, height: float) -> str:
        theme = self.theme
        return (
            f'<text x="{_num(width - theme.margin_px)}" '
            f'y="{_num(height - theme.footer_from_bottom_px)}" text-anchor="end" '
            f'font-family="{_attr(theme.font_stack)}" font-size="{_num(theme.footer_px)}" '
            f'fill="{_attr(theme.muted)}">{scene.order + 1}</text>'
        )

    # -- content extraction -----------------------------------------------------
    def _content(
        self, scene: SlideScene, media: Mapping[str, bytes]
    ) -> tuple[flow.Header, tuple[flow.Block, ...]]:
        """Turn a scene into (heading, body blocks), both in reading order."""

        entries: list[_Entry] = []
        for obj in sorted(scene.objects, key=lambda o: o.reading_order):
            entry = self._entry(obj, media)
            if entry is not None:
                entries.append(entry)
        if not entries:
            return flow.Header(), ()

        title_index = self._title_index(entries)
        if title_index is None:
            header, body = flow.Header(), entries
        else:
            kicker_index = self._kicker_index(entries, title_index)
            subtitle_index = self._subtitle_index(entries, title_index)
            header = flow.Header(
                kicker=entries[kicker_index].text if kicker_index is not None else None,
                title=entries[title_index].text,
                subtitle=entries[subtitle_index].text if subtitle_index is not None else None,
            )
            skip = {title_index, kicker_index, subtitle_index} - {None}
            body = [entry for index, entry in enumerate(entries) if index not in skip]
        return header, tuple(self._budget_pictures(header, self._blocks(body)))

    def _budget_pictures(
        self, header: flow.Header, blocks: list[flow.Block]
    ) -> list[flow.Block]:
        """Divide the slide's whole picture budget between its picture blocks.

        The budget is a *slide* budget, not a per-block one: a deck that interleaves
        a picture with every line would otherwise spend several body-heights on
        pictures and push its own text off the page. A picture-only slide may use
        the whole body; a mixed slide keeps pictures to their share.
        """

        indices = [
            index for index, block in enumerate(blocks) if isinstance(block, flow.PictureBlock)
        ]
        if not indices:
            return blocks
        width, height = float(self.config.width_px), float(self.config.height_px)
        body = flow.reference_body_height(header, self.theme, width, height)
        mixed = any(
            isinstance(block, (flow.TextBlock, flow.TableBlock, flow.PanelBlock))
            for block in blocks
        )
        share = body * (self.theme.picture_budget if mixed else 1.0) / len(indices)
        for index in indices:
            block = blocks[index]
            blocks[index] = flow.PictureBlock(block.images, max_height=share)
        return blocks

    def _entry(self, obj: ShapeObject, media: Mapping[str, bytes]) -> Optional[_Entry]:
        if obj.kind == "group" or obj.placeholder in _CHROME_PLACEHOLDERS:
            return None
        if obj.kind == "picture":
            image = self._picture(obj, media)
            return _Entry(kind="picture", obj=obj, image=image, text=image.label)
        if obj.kind == "table" and obj.table:
            rows, weights = _table_data(obj)
            if rows:
                return _Entry(kind="table", obj=obj, rows=rows, weights=weights)
            return None
        if obj.kind in _PANEL_KINDS:
            return _Entry(
                kind="panel",
                obj=obj,
                text=f"{obj.kind}: {obj.name or _basename(obj.media_ref)}",
            )
        paragraphs, size, text = self._paragraphs(obj)
        if not paragraphs:
            return None
        return _Entry(kind="text", obj=obj, paragraphs=paragraphs, size=size, text=text)

    def _paragraphs(self, obj: ShapeObject) -> tuple[tuple[flow.Paragraph, ...], float, str]:
        """The flow paragraphs of a text object, plus its largest size and text."""

        cleaned: list[tuple[TextParagraph, tuple[flow.Span, ...]]] = []
        for paragraph in obj.paragraphs:
            spans = tuple(
                flow.Span(run.text, bool(run.bold), bool(run.italic))
                for run in (paragraph.runs or ())
                if run.text
            )
            if not spans:
                fallback = paragraph.text or ""
                if not fallback.strip():
                    continue
                spans = (flow.Span(fallback),)
            if not "".join(span.text for span in spans).strip():
                continue
            cleaned.append((paragraph, spans))
        if not cleaned:
            return (), 0.0, ""

        listed = len(cleaned) > 1
        size = max(
            (
                float(run.size_pt)
                for paragraph, _spans in cleaned
                for run in (paragraph.runs or ())
                if run.size_pt
            ),
            default=0.0,
        )
        paragraphs = tuple(
            flow.Paragraph(
                spans=spans,
                level=max(0, int(paragraph.level or 0)),
                marker=_bullet_marker(paragraph, listed=listed),
            )
            for paragraph, spans in cleaned
        )
        text = " ".join("".join(span.text for span in spans) for _paragraph, spans in cleaned)
        return paragraphs, size, text

    def _picture(self, obj: ShapeObject, media: Mapping[str, bytes]) -> flow.Picture:
        crop = obj.crop or {}
        return flow.Picture(
            media_ref=obj.media_ref,
            label=_basename(obj.media_ref) or obj.name or "image",
            aspect=self._aspect(obj, media),
            crop=(
                float(crop.get("left") or 0.0),
                float(crop.get("top") or 0.0),
                float(crop.get("right") or 0.0),
                float(crop.get("bottom") or 0.0),
            ),
        )

    @staticmethod
    def _aspect(obj: ShapeObject, media: Mapping[str, bytes]) -> float:
        """The picture's own ratio: the file header, else the source frame."""

        payload = media.get(obj.media_ref) if obj.media_ref else None
        if payload:
            size = image_size(payload)
            if size and size[1]:
                return max(0.05, size[0] / size[1])
        bounds = obj.bounds
        if bounds is not None and bounds.width and bounds.height:
            return max(0.05, bounds.width / bounds.height)
        return 1.4

    def _blocks(self, entries: list[_Entry]) -> list[flow.Block]:
        """Fold the body entries into flow blocks.

        Consecutive text entries at the same emphasis are merged into *one* block:
        an art-directed deck writes each bullet in its own text box, and treating
        each box as its own block would spend the whole page on inter-block gaps
        and lose the fact that they are one list. Consecutive pictures are grouped
        into one row-block instead.
        """

        base = _nominal_size(entries)
        blocks: list[flow.Block] = []
        pending: list[flow.Picture] = []
        paragraphs: list[flow.Paragraph] = []
        emphasis: Optional[str] = None

        def flush_pictures() -> None:
            if pending:
                blocks.append(flow.PictureBlock(tuple(pending)))
                pending.clear()

        def flush_text() -> None:
            if paragraphs:
                blocks.append(flow.TextBlock(tuple(paragraphs), emphasis=emphasis or "body"))
                paragraphs.clear()

        for entry in entries:
            if entry.kind == "picture":
                flush_text()
                if entry.image is not None:
                    pending.append(entry.image)
                continue
            flush_pictures()
            if entry.kind == "text" and entry.paragraphs:
                row = _emphasis(entry.size, base)
                if paragraphs and row != emphasis:
                    flush_text()
                emphasis = row
                paragraphs.extend(entry.paragraphs)
            elif entry.kind == "table":
                flush_text()
                blocks.append(flow.TableBlock(rows=entry.rows, weights=entry.weights))
            elif entry.kind == "panel":
                flush_text()
                blocks.append(flow.PanelBlock(label=entry.text))
        flush_pictures()
        flush_text()
        return blocks

    # -- heading selection ------------------------------------------------------
    @staticmethod
    def _title_index(entries: list[_Entry]) -> Optional[int]:
        """Which block is the slide's heading (hoisted to the top of the column)."""

        for index, entry in enumerate(entries):
            if entry.kind == "text" and entry.obj.placeholder in _TITLE_PLACEHOLDERS:
                return index
        text_indices = [index for index, entry in enumerate(entries) if entry.kind == "text"]
        if not text_indices:
            # A table- or picture-only slide has no heading to hoist.
            return None
        largest = max(entries[index].size for index in text_indices)
        if largest <= 0.0:
            # No resolved type scale (a package with no master): the first text
            # block is the heading, which is where a deck puts it.
            return text_indices[0]
        return next(index for index in text_indices if entries[index].size >= largest - 0.01)

    @staticmethod
    def _kicker_index(entries: list[_Entry], title_index: int) -> Optional[int]:
        """The short line directly above the heading (an eyebrow/kicker)."""

        if title_index == 0:
            return None
        entry = entries[title_index - 1]
        if entry.kind != "text" or len(entry.paragraphs) != 1:
            return None
        if len(entry.text) > 80 or any(paragraph.marker for paragraph in entry.paragraphs):
            return None
        if entry.size > entries[title_index].size + 0.01:
            return None
        return title_index - 1

    @staticmethod
    def _subtitle_index(entries: list[_Entry], title_index: int) -> Optional[int]:
        """The short line directly below the heading (a subtitle)."""

        if title_index + 1 >= len(entries):
            return None
        entry = entries[title_index + 1]
        title = entries[title_index]
        if entry.kind != "text" or len(entry.paragraphs) > 2:
            return None
        if len(entry.text) < 8 or len(entry.text) > 120:
            # A two-character fragment is a list number, not a subtitle.
            return None
        if any(paragraph.marker for paragraph in entry.paragraphs):
            return None
        if entry.size > title.size + 0.01:
            return None
        return title_index + 1


__all__ = [
    "TEXT_OVERFLOW_PREFIX",
    "ThemedSvgRenderer",
]
