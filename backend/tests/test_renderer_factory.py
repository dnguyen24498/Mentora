"""V0-019: the render-mode registry — ``faithful`` is the default, ``themed`` an option.

The mode is part of the renderer identity and the package cache key, so the two
modes can never be confused for one another: they share a ``RenderConfig`` but
must never share a content-package version.
"""

from __future__ import annotations

import pytest

from app.common.errors import AppError, ErrorCode
from app.compiler.package_builder.builder import content_package_version
from app.compiler.renderers.base import RenderConfig
from app.compiler.renderers.factory import (
    DEFAULT_RENDER_MODE,
    MODE_FAITHFUL,
    MODE_THEMED,
    RENDER_MODES,
    UnknownRenderModeError,
    build_renderers,
    create_renderer,
)
from app.compiler.renderers.structural import StructuralSvgRenderer
from app.compiler.renderers.themed import ThemedSvgRenderer


def test_faithful_is_the_default_mode():
    """V0-019 v5: the product renders the deck's own layout by default."""

    assert DEFAULT_RENDER_MODE == MODE_FAITHFUL == "faithful"
    assert set(RENDER_MODES) == {"themed", "faithful"}


def test_create_renderer_selects_the_implementation(object_store):
    assert isinstance(create_renderer(MODE_THEMED, object_store), ThemedSvgRenderer)
    assert isinstance(create_renderer(MODE_FAITHFUL, object_store), StructuralSvgRenderer)
    assert isinstance(create_renderer(object_store=object_store), StructuralSvgRenderer)


def test_build_renderers_covers_every_mode_with_one_object_store(object_store, render_config):
    renderers = build_renderers(object_store, render_config)

    assert set(renderers) == set(RENDER_MODES)
    assert renderers[MODE_THEMED].identity().name != renderers[MODE_FAITHFUL].identity().name
    assert renderers[MODE_THEMED].inspect_support().fidelity_ceiling == "THEMED_RENDERED"
    assert renderers[MODE_FAITHFUL].inspect_support().fidelity_ceiling == "STRUCTURAL_RENDERED"


def test_an_unknown_mode_is_a_client_error(object_store):
    with pytest.raises(UnknownRenderModeError) as error:
        create_renderer("cinematic", object_store)

    assert isinstance(error.value, AppError)
    assert error.value.code is ErrorCode.INVALID_REQUEST
    assert error.value.http_status == 400


def test_the_two_modes_cannot_share_a_package_version(object_store):
    """Only the renderer identity separates the modes in the package cache key."""

    themed = create_renderer(MODE_THEMED, object_store, RenderConfig())
    faithful = create_renderer(MODE_FAITHFUL, object_store, RenderConfig())
    themed_identity = themed.identity()
    faithful_identity = faithful.identity()

    assert themed_identity.name != faithful_identity.name

    def version(name: str) -> str:
        # An identical config hash: the identity is what must keep them apart.
        return content_package_version("a" * 64, config_hash="same", renderer=name)

    assert version(themed_identity.name) != version(faithful_identity.name)
