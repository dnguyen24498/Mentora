"""Grouping-preserving flow layout for the platform theme (V0-019).

The ``themed`` mode does **not** reproduce the author's slide: a real deck's
geometry is art-directed for the author's fonts on the author's grid, and copying
it onto the platform's typeface and palette is what produced overlapping, ugly
slides. It does not flatten the slide into one column either: a deck's *grouping*
is content, not decoration — three cards stay three cards, an icon stays beside
its own label — and pulling that apart is what makes a re-flow read as nonsense.

So the layout keeps the author's **grouping** and owns everything else. The
structure is recovered from the source geometry alone (:func:`structure`): a
whitespace gap that spans a region splits it, the wider gap winning, so a region
becomes a :class:`Stack` (a horizontal gap, top-to-bottom) or a :class:`Row` (a
vertical gap, side-by-side) and every cell recurses. The platform then re-measures
and re-styles each cell in its own type scale: the author's fonts, sizes, colours,
fills and exact positions are never copied.

Why this cannot overlap
-----------------------
Within a region the layout is **one measuring pass over a cursor**: every block is
measured (wrapped lines → a height), placed at the cursor, and the cursor advances
by exactly that measured height. Across a :class:`Row` the cells are laid out into
**disjoint x-intervals** whose widths sum to the region. Both rules hold
recursively, so a block can only touch its neighbour if neither held —
``tests/test_flow_layout.py`` asserts the invariant pairwise over the emitted
geometry rather than trusting the argument.

A row whose cells each hold more than one block is drawn as a *card* (a flat
``theme.surface`` panel, no border): the author asked for a grid, and the flat fill
is how the theme says "these belong together".

The trade-off is honest and bounded: because the metrics are estimated
(``textmetrics.py``, no bundled font), a line may break a word early. It can
never push a block into its neighbour, and the platform's own chrome (the page
number) is placed in a strip the flow is never allowed to enter.

Fit policy
----------
Content is fitted by shrinking the whole type scale down a fixed ladder
(:data:`LADDER`), which keeps the *relationships* between title, body and table
sizes intact and gives two similar slides the same look. Only if even the ladder
floor cannot hold the content does the layout shrink continuously to
``theme.min_scale`` and, past that, report ``overflow`` for review (the renderer
then drops its own page number so nothing is covered and flags the scene).

Everything here is a pure function of its inputs: no clock, no host fonts, no
mapping iteration order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence, Union

from app.compiler.renderers import textmetrics
from app.compiler.renderers.mentora_theme import MentoraTheme

#: Type-scale ladder tried, largest first. A discrete ladder (rather than a
#: continuous fit) keeps the platform's type *relationships* intact and gives two
#: slides with similar density the same look.
LADDER: tuple[float, ...] = (1.0, 0.94, 0.88, 0.82, 0.76, 0.70, 0.64, 0.58)

#: A float tolerance for "does it fit" and "do these boxes touch".
EPSILON = 0.01

#: A cell that is only a number, a percentage, a date or a currency amount.
_NUMERIC = re.compile(r"^[+-]?[\d][\d\s.,]*\s*(%|\u20ab|\u20ac|\$|usd|vnd)?$", re.IGNORECASE)


# -- content (what the slide says) -------------------------------------------------
@dataclass(frozen=True)
class Span:
    """A run of text with one emphasis. The theme owns colour and family."""

    text: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class Paragraph:
    spans: tuple[Span, ...]
    level: int = 0
    #: Bullet glyph drawn to the left of the paragraph's first line, if any.
    marker: Optional[str] = None


@dataclass(frozen=True)
class TextBlock:
    paragraphs: tuple[Paragraph, ...]
    #: The theme type-scale row this block is drawn in: ``lead`` (a big source
    #: statement), ``body``, or ``caption`` (source fine print). The theme owns the
    #: sizes; the source only says which row, so a 40 pt statistic still reads as a
    #: statement next to a 12 pt note.
    emphasis: str = "body"


@dataclass(frozen=True)
class TableBlock:
    rows: tuple[tuple[str, ...], ...]
    #: Relative column widths; empty means "measure the content".
    weights: tuple[float, ...] = ()


@dataclass(frozen=True)
class Picture:
    media_ref: Optional[str]
    label: str
    #: Frame aspect ratio (width / height) used to size the picture.
    aspect: float
    #: ``a:srcRect`` crop fractions ``(left, top, right, bottom)``.
    crop: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class PictureBlock:
    """One or more pictures laid out side by side (a logo strip, a photo grid)."""

    images: tuple[Picture, ...]
    #: Absolute height budget, in px at the reference scale, shared by the block's
    #: rows. The caller divides the slide's whole picture budget between the blocks
    #: so a slide with many interleaved pictures cannot spend the page on them.
    #: ``0`` falls back to a share of the body box.
    max_height: float = 0.0


@dataclass(frozen=True)
class PanelBlock:
    """A content kind the platform cannot redraw (chart, SmartArt, diagram)."""

    label: str


Block = Union[TextBlock, TableBlock, PictureBlock, PanelBlock]


# -- structure (what belongs with what) --------------------------------------------
@dataclass(frozen=True)
class Item:
    """One content item with the source geometry the structure is derived from."""

    box: "Box"
    #: Adjacent items with the same key belong to one run (a list, a picture
    #: strip). ``""`` never merges.
    key: str = ""


@dataclass(frozen=True)
class Run:
    """A vertical run of items that belong together (resolves to a ``Leaf``)."""

    indices: tuple[int, ...]


@dataclass(frozen=True)
class Leaf:
    """A region's content: the blocks of one cell, laid out top to bottom."""

    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Row:
    """Side-by-side cells, sized in proportion to the source's own columns."""

    cells: tuple["Node", ...]
    #: The source extents the cells' widths are proportional to; empty = equal.
    weights: tuple[float, ...] = ()


@dataclass(frozen=True)
class Stack:
    """A vertical sequence of groups, separated by the theme's group gap."""

    children: tuple["Node", ...]


#: A resolved layout node: its leaves carry the themed blocks.
Node = Union[Leaf, Row, Stack]
#: ``structure()``'s output, before its runs are resolved to leaves.
Structure = Union[Run, Row, Stack]


@dataclass(frozen=True)
class Header:
    """The hoisted heading: what the teacher reads first."""

    kicker: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None


# -- layout (where it goes) --------------------------------------------------------
@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def overlaps(self, other: "Box", tolerance: float = 0.5) -> bool:
        """True when the two boxes share area (touching edges do not count)."""

        return (
            self.x + tolerance < other.right
            and other.x + tolerance < self.right
            and self.y + tolerance < other.bottom
            and other.y + tolerance < self.bottom
        )


@dataclass(frozen=True)
class TextLine:
    spans: tuple[Span, ...]
    size: float
    height: float
    x: float
    y: float
    anchor: str = "start"
    marker: Optional[str] = None
    marker_x: float = 0.0

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    @property
    def baseline(self) -> float:
        """Baseline offset used by the SVG emitter (0.82 em below the line top)."""

        return self.y + self.size * 0.82

    @property
    def width(self) -> float:
        return sum(
            textmetrics.measure(span.text, self.size, bold=span.bold, italic=span.italic)
            for span in self.spans
        )

    @property
    def box(self) -> Box:
        return Box(self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class PlacedText:
    box: Box
    lines: tuple[TextLine, ...]
    #: "title" | "kicker" | "subtitle" | "body" — the theme styles by role.
    role: str = "body"
    kind: str = "text"


@dataclass(frozen=True)
class PlacedRule:
    box: Box
    kind: str = "rule"


@dataclass(frozen=True)
class TableCell:
    box: Box
    lines: tuple[TextLine, ...]
    header: bool = False
    band: bool = False


@dataclass(frozen=True)
class PlacedTable:
    box: Box
    cells: tuple[TableCell, ...]
    kind: str = "table"


@dataclass(frozen=True)
class PlacedPicture:
    box: Box
    image: Picture
    kind: str = "picture"


@dataclass(frozen=True)
class PlacedPanel:
    box: Box
    label: str
    kind: str = "panel"


Placed = Union[PlacedText, PlacedRule, PlacedTable, PlacedPicture, PlacedPanel]


@dataclass(frozen=True)
class LayoutResult:
    items: tuple[Placed, ...]
    #: The box the body flowed into (below the header, above the chrome strip).
    body_box: Box
    scale: float
    #: True when the content did not fit even at ``theme.min_scale``: the renderer
    #: flags the scene and leaves the bottom strip clear instead of covering it.
    overflow: bool = False
    #: Card fills, drawn behind the content. They are *backgrounds*: they contain
    #: their cell's boxes, so they are excluded from the no-overlap invariant.
    surfaces: tuple[Box, ...] = ()

    def boxes(self) -> tuple[Box, ...]:
        """Every placed box, for the no-overlap invariant."""

        return tuple(item.box for item in self.items)


# -- structure detection -----------------------------------------------------------
#: How deep the geometry is allowed to nest (a card inside a row inside the body).
MAX_STRUCTURE_DEPTH = 12


def _spans(items: Sequence[Item], indices: Sequence[int], axis: str) -> list[tuple[float, float, int]]:
    """Each item's interval on one axis, sorted by where it starts."""

    if axis == "x":
        return sorted((items[i].box.x, items[i].box.right, i) for i in indices)
    return sorted((items[i].box.y, items[i].box.bottom, i) for i in indices)


def _best_split(
    spans: Sequence[tuple[float, float, int]], min_gap: float
) -> Optional[tuple[float, list[int], list[int]]]:
    """The widest empty band on this axis that spans the region.

    Returned as ``(gap, before, after)``: the region is cut there and each side is
    recursed into. Cutting only at the *widest* band is what keeps a card grid
    together — a narrower seam between two of a card's own lines can only be reached
    once the cards themselves have been separated.
    """

    best: Optional[tuple[float, int]] = None
    reach = spans[0][1]
    for cut, (low, _high, _index) in enumerate(spans[1:], start=1):
        if low - reach > min_gap and (best is None or low - reach > best[0]):
            best = (low - reach, cut)
        reach = max(reach, spans[cut][1])
    if best is None:
        return None
    gap, cut = best
    return gap, [span[2] for span in spans[:cut]], [span[2] for span in spans[cut:]]


def _extent(items: Sequence[Item], indices: Sequence[int], axis: str) -> float:
    """How much room a region's items take on one axis (the source proportion)."""

    if axis == "x":
        return max(items[i].box.right for i in indices) - min(items[i].box.x for i in indices)
    return max(items[i].box.bottom for i in indices) - min(items[i].box.y for i in indices)


def _columns_are_substantial(
    items: Sequence[Item], split: tuple[float, list[int], list[int]], indices: Sequence[int], share: float
) -> bool:
    """True when both sides of a vertical cut are real columns, not a sliver.

    An icon is a few percent of its card's width. Cutting the icon column off the
    text column would separate every icon from the label it belongs to, so when a
    side is that narrow the region is read as *rows* instead: the icon and its
    label end up in one row, which is the whole point of keeping the grouping.
    """

    _gap, left, right = split
    width = _extent(items, indices, "x")
    if width <= 0.0:
        return False
    smallest = min(_extent(items, left, "x"), _extent(items, right, "x"))
    return smallest >= share * width


def _run_key(items: Sequence[Item], run: Structure) -> str:
    keys = {items[index].key for index in run.indices}
    return next(iter(keys)) if len(keys) == 1 else ""


def _coalesce(items: Sequence[Item], children: Sequence[Structure]) -> tuple[Structure, ...]:
    """Fold adjacent runs of one key back together: they are one list.

    The gap search splits a list of full-width one-line boxes into a run per line;
    that is a split by whitespace, not by meaning, so the neighbours are rejoined
    and the leaf builder gets the list it expects.
    """

    merged: list[Structure] = []
    for child in children:
        if merged and isinstance(child, Run) and isinstance(merged[-1], Run):
            previous = merged[-1]
            key = _run_key(items, previous)
            if key and key == _run_key(items, child):
                merged[-1] = Run(tuple(sorted(previous.indices + child.indices)))
                continue
        merged.append(child)
    return tuple(merged)


def _flatten(items: Sequence[Item], node: Structure) -> Structure:
    """Fold same-axis nesting together: a row of rows *is* one row of cells.

    Cutting at one band at a time (so a card grid survives) leaves a binary tree;
    a row of six cells must read as six cells, not as three levels of two, or the
    card test would see an intermediate "row" as content and the gaps would
    multiply. Flattening restores the flat row and re-runs the list merge.
    """

    if isinstance(node, Run):
        return node
    if isinstance(node, Row):
        cells: list[Structure] = []
        weights: list[float] = []
        for index, cell in enumerate(node.cells):
            weight = node.weights[index] if index < len(node.weights) else 0.0
            inner = _flatten(items, cell)
            if isinstance(inner, Row) and inner.cells:
                shares = inner.weights if len(inner.weights) == len(inner.cells) else ()
                total = sum(shares) or float(len(inner.cells))
                for position, grandchild in enumerate(inner.cells):
                    cells.append(grandchild)
                    weights.append(weight * ((shares[position] if shares else 1.0) / total))
            else:
                cells.append(inner)
                weights.append(weight)
        if len(cells) == 1:
            return cells[0]
        return Row(tuple(cells), tuple(weights))

    children: list[Structure] = []
    for child in node.children:
        inner = _flatten(items, child)
        if isinstance(inner, Stack):
            children.extend(inner.children)
        else:
            children.append(inner)
    merged = _coalesce(items, tuple(children))
    if len(merged) == 1:
        return merged[0]
    return Stack(merged)


def structure(
    items: Sequence[Item],
    *,
    min_gap: float,
    min_column_share: float = 0.12,
    max_depth: int = MAX_STRUCTURE_DEPTH,
) -> Structure:
    """Recover the author's rows and columns from the source geometry alone.

    A whitespace band spanning the region splits it, and the wider of the two axes
    wins: a slide's banner comes off the top before its card row splits into cards,
    and each card's own icon/label rows split *inside* the card. A region with no
    such band is left as one reading-order run, which is what keeps a plain bullet
    slide a single column.
    """

    root = _split(items, tuple(range(len(items))), 0, min_gap, min_column_share, max_depth)
    return _flatten(items, root)


def _split(
    items: Sequence[Item],
    indices: tuple[int, ...],
    depth: int,
    min_gap: float,
    min_column_share: float,
    max_depth: int,
) -> Structure:
    if len(indices) <= 1 or depth >= max_depth:
        return Run(tuple(sorted(indices)))

    x_split = _best_split(_spans(items, indices, "x"), min_gap)
    y_split = _best_split(_spans(items, indices, "y"), min_gap)
    if x_split is None and y_split is None:
        return Run(tuple(sorted(indices)))

    columns = x_split is not None and (
        y_split is None
        or _columns_are_substantial(items, x_split, indices, min_column_share)
    )
    if columns:
        _gap, left, right = x_split  # type: ignore[misc]
        cells = (
            _split(items, tuple(left), depth + 1, min_gap, min_column_share, max_depth),
            _split(items, tuple(right), depth + 1, min_gap, min_column_share, max_depth),
        )
        return Row(cells, (_extent(items, left, "x"), _extent(items, right, "x")))

    _gap, top, bottom = y_split  # type: ignore[misc]
    children = (
        _split(items, tuple(top), depth + 1, min_gap, min_column_share, max_depth),
        _split(items, tuple(bottom), depth + 1, min_gap, min_column_share, max_depth),
    )
    return Stack(_coalesce(items, children))


def resolve(node: Structure, leaf) -> Node:
    """Resolve a structure's runs into leaves (``leaf(indices) -> Leaf``)."""

    if isinstance(node, Run):
        return leaf(node.indices)
    if isinstance(node, Row):
        return Row(tuple(resolve(cell, leaf) for cell in node.cells), node.weights)
    return Stack(tuple(resolve(child, leaf) for child in node.children))


# -- wrapping ----------------------------------------------------------------------
def _words(spans: Sequence[Span]) -> list[list[Span]]:
    """Split runs into whitespace-separated words, keeping each word's styling."""

    words: list[list[Span]] = []
    word: list[Span] = []

    def flush() -> None:
        if word:
            words.append(list(word))
            word.clear()

    for span in spans:
        buffer = ""
        for character in span.text:
            if character.isspace():
                if buffer:
                    word.append(Span(buffer, span.bold, span.italic))
                    buffer = ""
                flush()
            else:
                buffer += character
        if buffer:
            word.append(Span(buffer, span.bold, span.italic))
    flush()
    return words


def _measure_spans(spans: Sequence[Span], size: float) -> float:
    return sum(
        textmetrics.measure(span.text, size, bold=span.bold, italic=span.italic)
        for span in spans
    )


def _spans_text(spans: Sequence[Span]) -> str:
    return "".join(span.text for span in spans)


def _split_word(word: Sequence[Span], size: float, max_width: float) -> list[list[Span]]:
    """Split a word that cannot fit a line into chunks that can."""

    chunks: list[list[Span]] = []
    current: list[Span] = []
    width = 0.0
    for span in word:
        for character in span.text:
            advance = textmetrics.measure(character, size, bold=span.bold, italic=span.italic)
            if current and width + advance > max_width:
                chunks.append(current)
                current, width = [], 0.0
            current.append(Span(character, span.bold, span.italic))
            width += advance
    if current:
        chunks.append(current)
    return chunks


def wrap_spans(spans: Sequence[Span], size: float, max_width: float) -> list[list[Span]]:
    """Greedy word wrap that keeps each word's emphasis. Never returns empty."""

    limit = max(8.0, max_width)
    units: list[tuple[list[Span], bool]] = []
    for word in _words(spans):
        if _measure_spans(word, size) <= limit:
            units.append((word, True))
        else:
            for index, chunk in enumerate(_split_word(word, size, limit)):
                units.append((chunk, index == 0))

    lines: list[list[Span]] = []
    line: list[Span] = []
    width = 0.0
    for unit, glue in units:
        unit_width = _measure_spans(unit, size)
        space = textmetrics.measure(" ", size) if (line and glue) else 0.0
        if line and width + space + unit_width > limit:
            lines.append(line)
            line, width = list(unit), unit_width
            continue
        if space:
            # The separator takes the preceding run's emphasis, so a phrase inside
            # one run stays one span (and one ``tspan`` in the output).
            previous = line[-1]
            line.append(Span(" ", previous.bold, previous.italic))
        line.extend(unit)
        width += space + unit_width
    lines.append(line if line else [])
    return [_merge_spans(line) for line in lines]


def _merge_spans(spans: Sequence[Span]) -> list[Span]:
    """Fold adjacent runs with the same emphasis into one span."""

    merged: list[Span] = []
    for span in spans:
        if merged and merged[-1].bold == span.bold and merged[-1].italic == span.italic:
            merged[-1] = Span(merged[-1].text + span.text, span.bold, span.italic)
        else:
            merged.append(span)
    return merged


def wrap_text(text: str, size: float, max_width: float, *, bold: bool = False) -> list[str]:
    """Wrap plain text (table cells, headings) into lines."""

    return [_spans_text(spans) for spans in wrap_spans((Span(text, bold),), size, max_width)]


# -- placement ---------------------------------------------------------------------
@dataclass(frozen=True)
class _Placed:
    items: tuple[Placed, ...]
    height: float
    surfaces: tuple[Box, ...] = ()


def _place_header(
    header: Header, theme: MentoraTheme, x: float, width: float, y: float, scale: float
) -> _Placed:
    items: list[Placed] = []
    cursor = y
    for role, text, size in (
        ("kicker", header.kicker, theme.kicker_px),
        ("title", header.title, theme.title_px),
        ("subtitle", header.subtitle, theme.subtitle_px),
    ):
        if not text:
            continue
        size_px = size * scale
        line_height = size_px * theme.line_spacing
        bold = role == "title"
        lines = wrap_text(text, size_px, width, bold=bold)
        height = len(lines) * line_height
        items.append(
            PlacedText(
                box=Box(x, cursor, width, height),
                lines=tuple(
                    TextLine(
                        spans=(Span(line, bold=bold),),
                        size=size_px,
                        height=line_height,
                        x=x,
                        y=cursor + index * line_height,
                    )
                    for index, line in enumerate(lines)
                ),
                role=role,
            )
        )
        cursor += height + theme.heading_gap_px * scale
    if items:
        cursor -= theme.heading_gap_px * scale
        cursor += theme.rule_gap_px * scale
        items.append(PlacedRule(box=Box(x, cursor, width, 1.0)))
        cursor += 1.0
    return _Placed(tuple(items), cursor - y)


def _place_text(
    block: TextBlock, theme: MentoraTheme, x: float, width: float, y: float, scale: float
) -> _Placed:
    factor = _emphasis_factor(theme, block.emphasis)
    size = theme.body_px * factor * scale
    line_height = size * theme.line_spacing
    step = theme.list_indent_px * factor * scale
    gap = theme.paragraph_gap_px * factor * scale
    lines: list[TextLine] = []
    cursor = y
    for index, paragraph in enumerate(block.paragraphs):
        if index:
            cursor += gap
        indent = paragraph.level * step
        text_x = x + indent + (step if paragraph.marker else 0.0)
        text_width = max(24.0, width - indent - (step if paragraph.marker else 0.0))
        for line_index, spans in enumerate(wrap_spans(paragraph.spans, size, text_width)):
            lines.append(
                TextLine(
                    spans=tuple(spans),
                    size=size,
                    height=line_height,
                    x=text_x,
                    y=cursor,
                    marker=paragraph.marker if line_index == 0 else None,
                    marker_x=x + indent,
                )
            )
            cursor += line_height
    height = cursor - y
    return _Placed(
        (
            PlacedText(
                box=Box(x, y, width, height),
                lines=tuple(lines),
                role=block.emphasis,
            ),
        ),
        height,
    )


def _emphasis_factor(theme: MentoraTheme, emphasis: str) -> float:
    """The theme's type-scale row for a text block's emphasis."""

    if emphasis == "lead":
        return theme.lead_scale
    if emphasis == "caption":
        return theme.caption_scale
    return theme.body_scale


def _column_widths(block: TableBlock, width: float, size: float) -> list[float]:
    rows = block.rows
    columns = max(len(row) for row in rows)
    if block.weights and len(block.weights) == columns and sum(block.weights) > 0:
        raw = [weight / sum(block.weights) for weight in block.weights]
    else:
        measured = []
        for column in range(columns):
            widest = max(
                (textmetrics.measure(row[column], size) for row in rows if column < len(row)),
                default=0.0,
            )
            measured.append(max(widest, size * 4.0))
        total = sum(measured)
        raw = [value / total for value in measured]
    # No column may be starved or dominate: clamp, then renormalize. The bounds are
    # loose on purpose — the author's proportions are kept unless they are extreme.
    clamped = [min(0.78, max(0.08, weight)) for weight in raw]
    total = sum(clamped)
    return [width * weight / total for weight in clamped]


def _column_aligns(rows: Sequence[Sequence[str]], columns: int) -> list[str]:
    aligns: list[str] = []
    for column in range(columns):
        values = [
            row[column].strip()
            for row in rows[1:]  # the first row is treated as the header
            if column < len(row) and row[column].strip()
        ]
        numeric = [value for value in values if _NUMERIC.match(value)]
        aligns.append("end" if values and len(numeric) >= 0.6 * len(values) else "start")
    return aligns


def _place_table(block: TableBlock, theme: MentoraTheme, x: float, width: float, y: float, scale: float) -> _Placed:
    rows = block.rows
    columns = max(len(row) for row in rows)
    size = theme.table_px * scale
    line_height = size * theme.line_spacing
    pad_x = theme.table_pad_x_px * scale
    pad_y = theme.table_pad_y_px * scale
    widths = _column_widths(block, width, size)
    aligns = _column_aligns(rows, columns)
    header_row = len(rows) > 1

    cells: list[TableCell] = []
    cursor = y
    for row_index, row in enumerate(rows):
        wrapped = [
            wrap_text(row[column] if column < len(row) else "", size, max(12.0, widths[column] - 2 * pad_x))
            for column in range(columns)
        ]
        row_height = max((len(lines) for lines in wrapped), default=1) * line_height + 2 * pad_y
        column_x = x
        for column in range(columns):
            lines = wrapped[column]
            text_x = column_x + pad_x
            anchor = "start"
            if aligns[column] == "end":
                text_x = column_x + widths[column] - pad_x
                anchor = "end"
            cells.append(
                TableCell(
                    box=Box(column_x, cursor, widths[column], row_height),
                    lines=tuple(
                        TextLine(
                            spans=(Span(line, bold=(header_row and row_index == 0)),),
                            size=size,
                            height=line_height,
                            x=text_x,
                            y=cursor + pad_y + index * line_height,
                            anchor=anchor,
                        )
                        for index, line in enumerate(lines)
                    ),
                    header=header_row and row_index == 0,
                    band=bool(row_index % 2),
                )
            )
            column_x += widths[column]
        cursor += row_height
    height = cursor - y
    return _Placed((PlacedTable(box=Box(x, y, width, height), cells=tuple(cells)),), height)


def _place_pictures(
    block: PictureBlock,
    theme: MentoraTheme,
    x: float,
    width: float,
    y: float,
    scale: float,
    body_height: float,
) -> _Placed:
    images = block.images
    per_row = max(1, min(theme.max_pictures_per_row, len(images)))
    rows = [images[start : start + per_row] for start in range(0, len(images), per_row)]
    # Pictures shrink with the type scale, so "shrink to fit" always makes progress.
    # The budget is fixed by the reference (scale-1.0) body box, the smallest one,
    # which keeps "does it fit" monotonic.
    share = block.max_height if block.max_height > 0.0 else body_height * theme.picture_budget
    row_cap = max(12.0, share * scale / len(rows))

    gap = theme.picture_gap_px * scale
    items: list[PlacedPicture] = []
    cursor = y
    for index, row in enumerate(rows):
        if index:
            cursor += gap
        cell_width = (width - gap * (len(row) - 1)) / len(row)
        height = max(12.0, min([row_cap] + [cell_width / max(0.05, image.aspect) for image in row]))
        column_x = x
        for image in row:
            fitted_height = min(height, cell_width / max(0.05, image.aspect))
            fitted_width = fitted_height * image.aspect
            items.append(
                PlacedPicture(
                    box=Box(
                        column_x + (cell_width - fitted_width) / 2,
                        cursor + (height - fitted_height) / 2,
                        fitted_width,
                        fitted_height,
                    ),
                    image=image,
                )
            )
            column_x += cell_width + gap
        cursor += height
    height = cursor - y
    return _Placed(tuple(items), height)


def _place_block(
    block: Block,
    theme: MentoraTheme,
    x: float,
    width: float,
    y: float,
    scale: float,
    body_height: float,
) -> _Placed:
    if isinstance(block, TextBlock):
        return _place_text(block, theme, x, width, y, scale)
    if isinstance(block, TableBlock):
        return _place_table(block, theme, x, width, y, scale)
    if isinstance(block, PictureBlock):
        return _place_pictures(block, theme, x, width, y, scale, body_height)
    height = theme.panel_px * scale
    return _Placed((PlacedPanel(box=Box(x, y, width, height), label=block.label),), height)


def _block_count(node: Node) -> int:
    """How many blocks a node draws (what decides whether a cell is a card)."""

    if isinstance(node, Leaf):
        return len(node.blocks)
    if isinstance(node, Row):
        return sum(_block_count(cell) for cell in node.cells)
    return sum(_block_count(child) for child in node.children)


def _cell_widths(weights: Sequence[float], available: float, min_share: float) -> list[float]:
    """Row cell widths in the source's own proportions, renormalized to fit.

    The proportions are the author's (a wide column stays wide) but every cell keeps
    a readable share, so an extreme source column cannot starve its neighbour.
    """

    count = len(weights)
    if not count:
        return []
    total = sum(weight for weight in weights if weight > 0.0)
    raw = [weight / total for weight in weights] if total > 0.0 else [1.0 / count] * count
    clamped = [max(min_share, share) for share in raw]
    normalizer = sum(clamped)
    return [available * share / normalizer for share in clamped]


def _place_leaf(
    node: Leaf,
    theme: MentoraTheme,
    x: float,
    width: float,
    y: float,
    scale: float,
    body_height: float,
) -> _Placed:
    items: list[Placed] = []
    cursor = y
    for index, block in enumerate(node.blocks):
        if index:
            cursor += theme.item_gap_px * scale
        placed = _place_block(block, theme, x, width, cursor, scale, body_height)
        items.extend(placed.items)
        cursor += placed.height
    return _Placed(tuple(items), cursor - y)


def _place_row(
    node: Row,
    theme: MentoraTheme,
    x: float,
    width: float,
    y: float,
    scale: float,
    body_height: float,
) -> _Placed:
    cells = node.cells
    gap = theme.column_gap_px * scale
    pad = theme.card_pad_px * scale
    available = max(1.0, width - gap * (len(cells) - 1))
    widths = _cell_widths(node.weights, available, theme.min_cell_share)
    cards = [_block_count(cell) > 1 for cell in cells]

    placed: list[tuple[float, float, bool, _Placed]] = []
    column_x = x
    for cell, cell_width, card in zip(cells, widths, cards):
        inset = pad if card else 0.0
        inner_width = max(24.0, cell_width - 2 * inset)
        result = _place_node(cell, theme, column_x + inset, inner_width, y + inset, scale, body_height)
        placed.append((column_x, cell_width, card, result))
        column_x += cell_width + gap

    height = max(
        (result.height + (2 * pad if card else 0.0) for _, _, card, result in placed),
        default=0.0,
    )
    items: list[Placed] = []
    surfaces: list[Box] = []
    for column_x, cell_width, card, result in placed:
        items.extend(result.items)
        if card:
            surfaces.append(Box(column_x, y, cell_width, height))
    return _Placed(tuple(items), height, tuple(surfaces))


def _place_node(
    node: Node,
    theme: MentoraTheme,
    x: float,
    width: float,
    y: float,
    scale: float,
    body_height: float,
) -> _Placed:
    if isinstance(node, Leaf):
        return _place_leaf(node, theme, x, width, y, scale, body_height)
    if isinstance(node, Row):
        return _place_row(node, theme, x, width, y, scale, body_height)

    items: list[Placed] = []
    surfaces: list[Box] = []
    cursor = y
    for index, child in enumerate(node.children):
        if index:
            cursor += theme.group_gap_px * scale
        placed = _place_node(child, theme, x, width, cursor, scale, body_height)
        items.extend(placed.items)
        surfaces.extend(placed.surfaces)
        cursor += placed.height
    return _Placed(tuple(items), cursor - y, tuple(surfaces))


@dataclass(frozen=True)
class _Attempt:
    items: tuple[Placed, ...]
    body_box: Box
    needed: float
    surfaces: tuple[Box, ...] = ()


def _attempt(
    body: Node,
    header: Header,
    theme: MentoraTheme,
    width: float,
    height: float,
    scale: float,
    body_height_ref: float,
) -> _Attempt:
    content_x = theme.margin_px
    content_width = max(160.0, width - 2 * theme.margin_px)
    content_top = theme.margin_px
    content_bottom = height - theme.bottom_zone_px

    heading = _place_header(header, theme, content_x, content_width, content_top, scale)
    items: list[Placed] = list(heading.items)
    cursor = content_top + heading.height
    body_top = cursor
    if heading.height > 0:
        cursor += theme.header_gap_px * scale
        body_top = cursor

    placed = _place_node(body, theme, content_x, content_width, cursor, scale, body_height_ref)
    items.extend(placed.items)
    cursor += placed.height

    return _Attempt(
        items=tuple(items),
        body_box=Box(content_x, body_top, content_width, max(0.0, content_bottom - body_top)),
        needed=cursor - content_top,
        surfaces=placed.surfaces,
    )


def reference_body_height(
    header: Header, theme: MentoraTheme, width: float, height: float
) -> float:
    """The body box height at the reference (largest) scale.

    It is the *smallest* body box a slide will get, so a picture budget derived
    from it can never grow as the type scale shrinks — which keeps "does it fit"
    monotonic in the scale. ``themed`` also uses it to divide the slide's picture
    budget between picture blocks *before* laying out.
    """

    available = (height - theme.bottom_zone_px) - theme.margin_px
    heading = _place_header(header, theme, theme.margin_px, width - 2 * theme.margin_px, 0.0, 1.0)
    gap = theme.header_gap_px if heading.height > 0 else 0.0
    return max(1.0, available - heading.height - gap)


def layout(
    *,
    body: Node,
    header: Header,
    theme: MentoraTheme,
    width: float,
    height: float,
) -> LayoutResult:
    """Fit a body structure and ``header`` into one page.

    Never overlaps; may overflow (which is reported, never hidden).
    """

    available = (height - theme.bottom_zone_px) - theme.margin_px
    body_height_ref = reference_body_height(header, theme, width, height)

    attempt = _attempt(body, header, theme, width, height, 1.0, body_height_ref)
    if attempt.needed <= available + EPSILON:
        return LayoutResult(attempt.items, attempt.body_box, 1.0, surfaces=attempt.surfaces)

    for scale in LADDER[1:]:
        attempt = _attempt(body, header, theme, width, height, scale, body_height_ref)
        if attempt.needed <= available + EPSILON:
            return LayoutResult(attempt.items, attempt.body_box, scale, surfaces=attempt.surfaces)

    # Even the ladder floor is too small a scale to hold the content. Shrink
    # continuously as far as the readable floor allows, then report what is left
    # over rather than dropping it.
    scale = LADDER[-1]
    for _ in range(8):
        if attempt.needed <= available + EPSILON:
            break
        shrink = available / attempt.needed
        adjusted = max(theme.min_scale, scale * shrink)
        if adjusted >= scale - 1e-6:
            break
        scale = adjusted
        attempt = _attempt(body, header, theme, width, height, scale, body_height_ref)

    return LayoutResult(
        attempt.items,
        attempt.body_box,
        scale,
        overflow=attempt.needed > available + EPSILON,
        surfaces=attempt.surfaces,
    )


def fitted(body: Node, header: Header, theme: MentoraTheme, width: float, height: float) -> bool:
    """True when the content fits without overflowing (used by the renderer/tests)."""

    return not layout(body=body, header=header, theme=theme, width=width, height=height).overflow


__all__ = [
    "LADDER",
    "Box",
    "Block",
    "Header",
    "Item",
    "Leaf",
    "LayoutResult",
    "Node",
    "PanelBlock",
    "Paragraph",
    "Picture",
    "PictureBlock",
    "PlacedPanel",
    "PlacedPicture",
    "PlacedRule",
    "PlacedTable",
    "PlacedText",
    "Row",
    "Run",
    "Span",
    "Stack",
    "Structure",
    "TableCell",
    "TableBlock",
    "TextBlock",
    "TextLine",
    "fitted",
    "layout",
    "reference_body_height",
    "resolve",
    "structure",
    "wrap_spans",
    "wrap_text",
]
