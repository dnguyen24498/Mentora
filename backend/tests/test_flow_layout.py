"""V0-019: the flow layout — one readable column that cannot overlap.

The renderer used to copy the author's geometry, which reproduced the author's
collisions on real decks. These tests pin the replacement contract:

* **no overlap, ever** — asserted pairwise over the geometry the layout returns,
  not argued from the algorithm;
* **the chrome strip is reserved** — the page number's band is outside every
  placed box, so platform chrome cannot cover content;
* **content survives the fit** — the type scale shrinks to fit, and content that
  still does not fit is *reported*, with every line still placed;
* **the reading order is the placement order**.
"""

from __future__ import annotations

import pytest

from app.compiler.renderers import flow
from app.compiler.renderers.mentora_theme import DEFAULT_THEME
from app.compiler.renderers.textmetrics import measure

THEME = DEFAULT_THEME
WIDTH = 1280.0
HEIGHT = 720.0
CONTENT_LEFT = THEME.margin_px
CONTENT_RIGHT = WIDTH - THEME.margin_px
CONTENT_BOTTOM = HEIGHT - THEME.bottom_zone_px


# -- builders ----------------------------------------------------------------------
def text_block(*lines: str, level: int = 0, marker: str | None = None) -> flow.TextBlock:
    return flow.TextBlock(
        paragraphs=tuple(
            flow.Paragraph(spans=(flow.Span(line),), level=level, marker=marker)
            for line in lines
        )
    )


def long_block(count: int) -> flow.TextBlock:
    return text_block(*[f"Paragraph {index} with a few words in it" for index in range(count)])


def picture(aspect: float, label: str = "image") -> flow.Picture:
    return flow.Picture(media_ref=f"ppt/media/{label}", label=label, aspect=aspect)


def table(rows: list[list[str]], weights: tuple[float, ...] = ()) -> flow.TableBlock:
    return flow.TableBlock(rows=tuple(tuple(row) for row in rows), weights=weights)


def place(*blocks: flow.Block, header: flow.Header | None = None) -> flow.LayoutResult:
    return flow.layout(
        blocks=blocks,
        header=header or flow.Header(),
        theme=THEME,
        width=WIDTH,
        height=HEIGHT,
    )


def assert_no_overlap(result: flow.LayoutResult) -> None:
    boxes = result.boxes()
    for index, box in enumerate(boxes):
        for other in boxes[index + 1 :]:
            assert not box.overlaps(other), f"{box} overlaps {other}"


# -- the invariant -----------------------------------------------------------------
def test_blocks_never_overlap():
    result = place(
        text_block("Heading line one", "Heading line two"),
        table([["Model", "BLEU"], ["Baseline", "24.1"], ["Ours", "31.7"]]),
        flow.PanelBlock(label="chart: Scores"),
        flow.PictureBlock((picture(2.0, "a.png"), picture(0.8, "b.png"))),
        long_block(6),
    )

    assert_no_overlap(result)
    assert not result.overflow


def test_blocks_are_placed_in_the_order_given():
    result = place(
        text_block("first"), text_block("second"), text_block("third")
    )

    tops = [item.box.y for item in result.items]
    assert tops == sorted(tops)
    contents = [
        line.text for item in result.items if isinstance(item, flow.PlacedText) for line in item.lines
    ]
    assert contents == ["first", "second", "third"]


def test_the_heading_is_placed_above_the_body():
    result = place(
        text_block("Body text"),
        header=flow.Header(kicker="KHOA", title="BÁO CÁO", subtitle="Hải Phòng"),
    )

    roles = [item.role for item in result.items if isinstance(item, flow.PlacedText)]
    assert roles[:3] == ["kicker", "title", "subtitle"]
    assert isinstance(result.items[3], flow.PlacedRule), "the heading gets a hairline rule"
    assert result.body_box.y > result.items[3].box.bottom


def test_no_placed_box_enters_the_chrome_strip():
    result = place(long_block(8), header=flow.Header(title="Title"))

    for item in result.items:
        assert item.box.bottom <= CONTENT_BOTTOM + flow.EPSILON, item
        assert item.box.x >= CONTENT_LEFT - flow.EPSILON, item
        assert item.box.right <= CONTENT_RIGHT + flow.EPSILON, item
    assert result.body_box.bottom <= CONTENT_BOTTOM + flow.EPSILON


def test_a_line_never_exceeds_its_column():
    result = place(long_block(4))
    text_items = [item for item in result.items if isinstance(item, flow.PlacedText)]

    for item in text_items:
        for line in item.lines:
            assert line.x >= item.box.x - flow.EPSILON
            assert line.x + line.width <= item.box.right + flow.EPSILON
            assert line.y >= item.box.y - flow.EPSILON
            assert line.y + line.height <= item.box.bottom + flow.EPSILON


# -- fitting -----------------------------------------------------------------------
def test_a_light_slide_uses_the_full_scale():
    result = place(text_block("A short line"))

    assert result.scale == 1.0
    assert not result.overflow


def test_dense_content_shrinks_the_type_scale_but_still_fits():
    result = place(long_block(22))

    assert 0.0 < result.scale < 1.0
    assert not result.overflow
    assert_no_overlap(result)
    tail = max(item.box.bottom for item in result.items)
    assert tail <= CONTENT_BOTTOM + flow.EPSILON


def test_the_ladder_is_only_used_until_the_content_fits():
    """A denser slide never gets a *larger* scale than a lighter one."""

    light = place(long_block(4)).scale
    heavy = place(long_block(16)).scale

    assert heavy <= light


def test_content_that_cannot_fit_is_flagged_but_never_dropped():
    result = place(long_block(600))

    assert result.overflow
    # Every paragraph is placed: the last one is in the output, just unreachable.
    placed = [
        line.text
        for item in result.items
        if isinstance(item, flow.PlacedText)
        for line in item.lines
    ]
    assert placed[-1] == "Paragraph 599 with a few words in it"
    assert len(placed) >= 600
    assert_no_overlap(result)


# -- tables ------------------------------------------------------------------------
def test_table_columns_fill_the_content_width():
    result = place(table([["Model", "BLEU", "Notes"], ["Baseline", "24.1", "ref"]]))
    placed = next(item for item in result.items if isinstance(item, flow.PlacedTable))

    assert placed.box.x == CONTENT_LEFT
    assert placed.box.right == pytest.approx(CONTENT_RIGHT)
    column_right = max(cell.box.right for cell in placed.cells)
    assert column_right == pytest.approx(CONTENT_RIGHT)


def test_numeric_columns_are_right_aligned():
    result = place(
        table([["Model", "BLEU", "Delta"], ["Baseline", "24.1", "-1.2"], ["Ours", "31.7", "+6.4"]])
    )
    placed = next(item for item in result.items if isinstance(item, flow.PlacedTable))

    by_column: dict[float, list[flow.TextLine]] = {}
    for cell in placed.cells:
        by_column.setdefault(cell.box.x, []).extend(cell.lines)
    columns = sorted(by_column)
    assert {line.anchor for line in by_column[columns[0]]} == {"start"}
    assert {line.anchor for line in by_column[columns[1]]} == {"end"}
    assert {line.anchor for line in by_column[columns[2]]} == {"end"}


def test_the_header_row_and_bands_are_marked_for_styling():
    result = place(table([["Model", "BLEU"], ["Baseline", "24.1"], ["Ours", "31.7"]]))
    placed = next(item for item in result.items if isinstance(item, flow.PlacedTable))
    rows = sorted({cell.box.y for cell in placed.cells})

    first = [cell for cell in placed.cells if cell.box.y == rows[0]]
    second = [cell for cell in placed.cells if cell.box.y == rows[1]]
    assert all(cell.header for cell in first)
    assert not any(cell.header for cell in second)
    assert all(cell.band for cell in second)


def test_source_column_widths_are_respected():
    rows = [["a" * 40, "b"], ["c" * 40, "d"]]
    result = place(table(rows, weights=(3.0, 1.0)))
    placed = next(item for item in result.items if isinstance(item, flow.PlacedTable))
    widths = sorted({round(cell.box.width, 3) for cell in placed.cells}, reverse=True)

    assert widths[0] == pytest.approx((CONTENT_RIGHT - CONTENT_LEFT) * 0.75, abs=0.5)


# -- pictures ----------------------------------------------------------------------
def test_pictures_are_laid_side_by_side_without_distortion():
    result = place(
        flow.PictureBlock((picture(2.0, "wide.png"), picture(0.5, "tall.png"), picture(1.0, "sq.png")))
    )
    placed = [item for item in result.items if isinstance(item, flow.PlacedPicture)]

    assert len(placed) == 3
    assert_no_overlap(result)
    for item in placed:
        assert item.box.height > 0
        assert item.box.width / item.box.height == pytest.approx(item.image.aspect, rel=1e-6)
        assert item.box.right <= CONTENT_RIGHT + flow.EPSILON
    lefts = [item.box.x for item in placed]
    assert lefts == sorted(lefts)


def test_a_picture_uses_its_height_budget():
    generous = place(flow.PictureBlock((picture(1.4),), max_height=400.0))
    meagre = place(flow.PictureBlock((picture(1.4),), max_height=80.0))

    big = next(item for item in generous.items if isinstance(item, flow.PlacedPicture))
    small = next(item for item in meagre.items if isinstance(item, flow.PlacedPicture))
    assert big.box.height > small.box.height
    assert big.box.height <= generous.body_box.height + flow.EPSILON
    assert small.box.height == pytest.approx(80.0, rel=1e-6)


def test_more_pictures_than_fit_a_row_wrap_onto_the_next_row():
    result = place(flow.PictureBlock(tuple(picture(1.0, f"{index}.png") for index in range(6))))
    placed = [item for item in result.items if isinstance(item, flow.PlacedPicture)]

    rows = sorted({round(item.box.y, 3) for item in placed})
    assert len(rows) == 2, "six pictures at four per row need two rows"
    assert_no_overlap(result)


# -- wrapping and metrics ----------------------------------------------------------
def test_wrapping_never_exceeds_the_column():
    words = " ".join("lorem" for _ in range(60))
    lines = flow.wrap_text(words, 19.0, 300.0)

    assert len(lines) > 1
    for line in lines:
        assert measure(line, 19.0) <= 300.0 + 0.01


def test_a_word_wider_than_the_column_is_split():
    lines = flow.wrap_text("x" * 400, 19.0, 200.0)

    assert len(lines) > 1
    assert "".join(lines) == "x" * 400


def test_paragraphs_keep_their_emphasis_and_levels():
    block = flow.TextBlock(
        paragraphs=(
            flow.Paragraph(spans=(flow.Span("Plain "), flow.Span("bold", bold=True))),
            flow.Paragraph(spans=(flow.Span("nested"),), level=1, marker="–"),
        )
    )
    result = place(block)
    lines = next(item for item in result.items if isinstance(item, flow.PlacedText)).lines

    assert [span.text for span in lines[0].spans] == ["Plain ", "bold"]
    assert lines[0].spans[1].bold is True
    assert lines[1].marker == "–"
    assert lines[1].x > lines[0].x, "a nested list level is indented"


def test_an_empty_block_still_occupies_a_line():
    result = place(flow.TextBlock(paragraphs=(flow.Paragraph(spans=(flow.Span(""),)),)))

    assert result.items
    assert result.items[0].box.height > 0


# -- determinism -------------------------------------------------------------------
def test_the_same_input_lays_out_identically():
    blocks = (
        text_block("First", "Second"),
        table([["a", "1"], ["b", "2"]]),
        flow.PictureBlock((picture(1.5),)),
    )
    first = place(*blocks, header=flow.Header(title="Title"))
    second = place(*blocks, header=flow.Header(title="Title"))

    assert first == second


def test_fitted_reports_the_overflow_state():
    assert flow.fitted((text_block("short"),), flow.Header(), THEME, WIDTH, HEIGHT) is True
    assert flow.fitted((long_block(600),), flow.Header(), THEME, WIDTH, HEIGHT) is False
