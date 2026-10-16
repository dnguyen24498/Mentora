"""V0-004 extraction corpus gate.

`acceptance criteria: known extraction corpus matches expected results`.
Every manifest item must have an executable builder, and every declared
expectation must hold.
"""

from __future__ import annotations

import pytest

from tests import corpus

MANIFEST = corpus.load_manifest()
ITEMS = MANIFEST["items"]


def test_every_manifest_item_has_a_builder():
    missing = [item["id"] for item in ITEMS if item["builder"] not in corpus.BUILDERS]
    assert not missing, f"corpus items without a builder: {missing}"


def test_every_builder_is_used_by_the_manifest():
    declared = {item["builder"] for item in ITEMS}
    unused = sorted(set(corpus.BUILDERS) - declared)
    assert not unused, f"builders not declared in the corpus manifest: {unused}"


def test_categories_are_declared():
    known = set(MANIFEST["categories"])
    unknown = sorted({item["category"] for item in ITEMS} - known)
    assert not unknown, f"items use undeclared categories: {unknown}"


@pytest.mark.parametrize("item", ITEMS, ids=[item["id"] for item in ITEMS])
def test_corpus_item_matches_expected_results(extractor, item):
    document = extractor.extract(corpus.build(item["builder"]), source_sha256="c" * 64)
    failures = corpus.check_expectations(document, item["expect"])
    assert not failures, f"{item['id']}: " + "; ".join(failures)
