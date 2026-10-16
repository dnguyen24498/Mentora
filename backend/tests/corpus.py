"""Executable extraction corpus.

`evaluation/manifests/pptx-corpus.json` declares the corpus *items* and the
expected observable results; this module supplies the deterministic package
builder for each item and asserts the expectations. Keeping the packages as code
(not binary fixtures) means the expected structure is explicit and reviewable —
the same convention the extractor tests use.

Adding a corpus item = add a builder here + an entry in the manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.compiler.models.ir import ContentIRDocument
from tests.fixtures import (
    REL_CHART,
    REL_IMAGE,
    build_pptx,
    chart_shape,
    group_shape,
    picture_shape,
    simple_pptx,
    table_shape,
    text_shape,
)

MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "evaluation" / "manifests" / "pptx-corpus.json"
)


def _simple() -> bytes:
    return simple_pptx()


def _notes() -> bytes:
    return build_pptx(
        [[text_shape(2, "Title", text="Attention", placeholder="title")]],
        notes={1: "Remember query/key/value\nAsk about scaling"},
    )


def _table() -> bytes:
    return build_pptx(
        [[table_shape(5, "Results", [["Model", "BLEU"], ["Baseline", "24.1"]])]]
    )


def _chart() -> bytes:
    return build_pptx(
        [[chart_shape(6, "Scores")]],
        extra_slide_rels={1: [("rIdChart", REL_CHART, "../charts/chart1.xml")]},
        extra_entries={"ppt/charts/chart1.xml": b"<c:chartSpace/>"},
    )


def _custom_fonts() -> bytes:
    return build_pptx(
        [
            [
                text_shape(2, "Title", text="Brand deck", font="Bree Serif", placeholder="title"),
                text_shape(3, "Body", text="Body copy", font="Inter Light"),
            ]
        ]
    )


def _vietnamese_fonts() -> bytes:
    return build_pptx(
        [
            [
                text_shape(
                    2,
                    "Title",
                    text="Bài giảng: Trí tuệ nhân tạo và học máy",
                    font="VNI-Times",
                    placeholder="title",
                ),
                text_shape(3, "Body", text="Câu hỏi kiểm tra: định nghĩa là gì?"),
            ]
        ]
    )


def _media() -> bytes:
    return build_pptx(
        [[picture_shape(4, "Figure", rel_id="rIdImg")]],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
        extra_entries={"ppt/media/image1.png": b"PNGDATA"},
    )


def _groups_nested() -> bytes:
    inner = group_shape(11, "Inner", [text_shape(12, "Leaf", text="deep-text")])
    return build_pptx(
        [
            [
                text_shape(2, "Top", text="top-text"),
                group_shape(10, "Outer", [inner, text_shape(13, "Mid", text="mid-text")]),
            ]
        ]
    )


def _broken_relationship() -> bytes:
    """A relationship id the slide never declares (dangling ``r:embed``)."""

    return build_pptx([[picture_shape(4, "Figure", rel_id="rIdMissing")]])


def _image_part_absent() -> bytes:
    """A declared image relationship whose target part is missing."""

    return build_pptx(
        [[picture_shape(4, "Figure", rel_id="rIdImg")]],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/missing.png")]},
    )


def _malformed_relationship_part() -> bytes:
    """A ``.rels`` part that is not well-formed XML."""

    return build_pptx(
        [[text_shape(2, "Keep", text="still-extracted")]],
        extra_entries={"ppt/slides/_rels/slide1.xml.rels": b"<Relationships><broken"},
    )


BUILDERS: dict[str, Callable[[], bytes]] = {
    "simple": _simple,
    "notes": _notes,
    "table": _table,
    "chart": _chart,
    "custom_fonts": _custom_fonts,
    "vietnamese_fonts": _vietnamese_fonts,
    "media": _media,
    "groups_nested": _groups_nested,
    "broken_relationship": _broken_relationship,
    "image_part_absent": _image_part_absent,
    "malformed_relationship_part": _malformed_relationship_part,
}


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def build(item_id: str) -> bytes:
    return BUILDERS[item_id]()


# -- expectation harness --------------------------------------------------------
def _all_texts(document: ContentIRDocument) -> str:
    return "\n".join(p.text for s in document.slides for o in s.objects for p in o.paragraphs)


def _all_fonts(document: ContentIRDocument) -> set[str]:
    return {font for s in document.slides for font in s.fonts()}


def _all_warnings(document: ContentIRDocument) -> str:
    parts = list(document.warnings)
    for scene in document.slides:
        parts.extend(scene.warnings)
    return "\n".join(parts)


def _all_kinds(document: ContentIRDocument) -> set[str]:
    return {o.kind for s in document.slides for o in s.objects}


def _all_media_refs(document: ContentIRDocument) -> set[str]:
    return {o.media_ref for s in document.slides for o in s.objects if o.media_ref}


def _all_tables(document: ContentIRDocument) -> list[list[list[str]]]:
    return [o.table for s in document.slides for o in s.objects if o.table is not None]


def check_expectations(document: ContentIRDocument, expect: dict[str, Any]) -> list[str]:
    """Return a list of human-readable failures (empty means the item matched)."""

    failures: list[str] = []

    if "slide_count" in expect and document.slide_count != expect["slide_count"]:
        failures.append(f"slide_count {document.slide_count} != {expect['slide_count']}")

    if "texts" in expect:
        haystack = _all_texts(document)
        for needle in expect["texts"]:
            if needle not in haystack:
                failures.append(f"missing text {needle!r}")

    if "fonts" in expect:
        fonts = _all_fonts(document)
        for needle in expect["fonts"]:
            if needle not in fonts:
                failures.append(f"missing font {needle!r} (got {sorted(fonts)})")

    if "kinds" in expect:
        kinds = _all_kinds(document)
        for needle in expect["kinds"]:
            if needle not in kinds:
                failures.append(f"missing kind {needle!r} (got {sorted(kinds)})")

    if "media_refs" in expect:
        refs = _all_media_refs(document)
        for needle in expect["media_refs"]:
            if needle not in refs:
                failures.append(f"missing media_ref {needle!r} (got {sorted(refs)})")

    if "tables" in expect:
        tables = _all_tables(document)
        for needle in expect["tables"]:
            if needle not in tables:
                failures.append(f"missing table {needle!r} (got {tables})")

    if "notes_contains" in expect:
        notes = "\n".join(s.notes or "" for s in document.slides)
        if expect["notes_contains"] not in notes:
            failures.append(f"notes do not contain {expect['notes_contains']!r}")

    if "min_objects" in expect:
        for scene in document.slides:
            if len(scene.objects) < expect["min_objects"]:
                failures.append(
                    f"slide {scene.order} has {len(scene.objects)} objects "
                    f"< {expect['min_objects']}"
                )

    if "warnings_contain" in expect:
        warnings = _all_warnings(document)
        for needle in expect["warnings_contain"]:
            if needle not in warnings:
                failures.append(f"missing warning {needle!r} (got {warnings!r})")

    return failures
