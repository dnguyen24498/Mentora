"""V0-005 render/fidelity corpus gate.

`evaluation/manifests/render-fidelity.json` declares, per deterministic corpus
item, the render outcome every slide must produce. This is the executable form of
"same engine/config gives stable logical output": the classification (fidelity,
missing fonts, publishability) must be exactly reproducible.

It runs the **default** render mode (V0-019: ``themed``), so the manifest's
``engine`` block names the renderer the application actually uses. The
``faithful`` mode's outcomes are asserted by ``tests/test_renderer_fidelity.py``
and ``tests/test_renderers.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.compiler.renderers.base import RenderBudget, RenderRequest
from tests import corpus

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "manifests" / "render-fidelity.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
ITEMS = MANIFEST["items"]


def _compile_one(extractor, renderer, item):
    """"Compile" one corpus item: extract + render every slide."""

    document = extractor.extract(corpus.build(item["builder"]), source_sha256="r" * 64)
    report = renderer.render(
        RenderRequest(document=document, identity=renderer.identity()),
        budget=RenderBudget(5.0, max_attempts=2),
    )
    return document, report


def test_every_item_uses_a_known_builder():
    missing = [i["id"] for i in ITEMS if i["builder"] not in corpus.BUILDERS]
    assert not missing, f"render corpus items without a builder: {missing}"


def test_manifest_engine_matches_the_local_renderer(default_renderer):
    identity = default_renderer.identity()
    declared = MANIFEST["engine"]
    assert identity.name == declared["renderer_id"]
    assert identity.version == declared["renderer_version"]
    assert identity.data_region == declared["data_region"]
    assert default_renderer.inspect_support().fidelity_ceiling == declared["fidelity_ceiling"]


@pytest.mark.parametrize("item", ITEMS, ids=[i["id"] for i in ITEMS])
def test_render_corpus_item_matches_expected_outcome(extractor, default_renderer, item):
    from app.compiler.renderers.base import RenderStatus
    from app.compiler.validators.fidelity import validate_render

    document, report = _compile_one(extractor, default_renderer, item)
    expect = item["expect"]

    # Every slide has a render or an explicit FAILED (V0-005 acceptance).
    assert len(report.results) == expect["slides"]
    assert [r.order for r in report.results] == list(range(expect["slides"]))
    for result in report.results:
        assert result.status is RenderStatus[expect["status"]]
        assert result.fidelity == expect["fidelity"]
        assert list(result.missing_fonts) == expect["missing_fonts"]

    validation = validate_render(document, report)
    assert validation.publishable is expect["publishable"]
    assert validation.requires_review is expect["requires_review"]


def test_classification_is_stable_across_runs(extractor, default_renderer):
    """Re-running the same item yields the same asset key and same fidelity."""

    item = next(i for i in ITEMS if i["id"] == "custom_fonts")
    _, first = _compile_one(extractor, default_renderer, item)
    _, second = _compile_one(extractor, default_renderer, item)

    assert [r.asset_ref for r in first.results] == [r.asset_ref for r in second.results]
    assert [r.fidelity for r in first.results] == [r.fidelity for r in second.results]
