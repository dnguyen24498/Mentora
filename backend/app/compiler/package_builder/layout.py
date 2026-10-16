"""Baseline package layout conventions (V0-006).

A Baseline Content Package is the immutable envelope built by the *baseline
builder* stage of ``docs/architecture/04_CONTENT_COMPILER.md``
(``…reveal semantics → Content IR → baseline builder → Validation``).

The conventions here are the contract for ``manifest.files[].path`` and are
documented in ``contracts/ctf/PACKAGE_LAYOUT.md``. They are deliberately simple
and deterministic: the same inputs always produce the same paths, so the
manifest is reproducible byte-for-byte.

``DEC-CONTENT-004``: the manifest is a *reference* envelope — it lists file
paths with checksums and content media types. It never inlines the scenes or the
lesson plan, and it is never listed inside its own ``files[]``.
"""

from __future__ import annotations

import re

#: The manifest is the envelope and the commit point of a package. It is written
#: last and is not listed in its own ``files[]`` (the checksum of the manifest
#: would otherwise have to include itself).
MANIFEST_FILENAME = "manifest.json"
LESSON_PLAN_FILENAME = "lesson-plan.json"
SCENE_DIRECTORY = "scenes"
ASSET_DIRECTORY = "assets"

MANIFEST_SCHEMA_VERSION = "1.0.0"
MEDIA_TYPE_JSON = "application/json"
MEDIA_TYPE_SVG = "image/svg+xml"
DEFAULT_ASSET_MEDIA_TYPE = "application/octet-stream"

#: Extensions whose bytes are a source document the runtime must never see
#: (``DEC-CONTENT-001``: runtime never parses original source documents, so a
#: package that carries one would reintroduce a parser dependency).
SOURCE_DOCUMENT_EXTENSIONS = (".pptx", ".ppt", ".pptm", ".ppsx", ".odp", ".pdf")

#: ``contracts/ctf/manifest.schema.json`` requires ``knowledge_index_version``.
#: Indexing is V0-014, and ``DEC-CONTENT-002`` requires a baseline package to be
#: usable without it, so a baseline package declares itself unindexed rather
#: than inventing an index version.
UNINDEXED = "unindexed"

#: Anything outside this set is replaced with ``-`` so a scene id (which is an
#: OOXML part path such as ``ppt/slides/slide1.xml``) becomes a flat filename.
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_component(value: str) -> str:
    """Filesystem-safe, deterministic form of an id (scene ids are part paths)."""

    cleaned = _UNSAFE.sub("-", value.strip()).strip("-")
    return cleaned or "unnamed"


def package_prefix(package_id: str) -> str:
    """Object-store prefix for one package (``DEC-CONTENT-005`` isolation)."""

    return f"packages/{_safe_component(package_id)}"


def scene_path(order: int, scene_id: str) -> str:
    """Path of one scene file. Zero-padded order keeps listings in lesson order."""

    return f"{SCENE_DIRECTORY}/{order:03d}-{_safe_component(scene_id)}.json"


def lesson_plan_path() -> str:
    return LESSON_PLAN_FILENAME


def asset_path(sha256: str, extension: str) -> str:
    """Asset path inside the package, content-addressed by the asset's digest.

    Assets are *copied* into the package (not merely referenced) so a published
    package stays immutable even if the compiler's asset store is later pruned.
    """

    return f"{ASSET_DIRECTORY}/{sha256}{extension}"


def extension_of(asset_ref: str) -> str:
    """Extension (with dot) of an asset reference, defaulting to ``.bin``."""

    tail = asset_ref.rsplit("/", 1)[-1]
    if "." in tail:
        return "." + tail.rsplit(".", 1)[-1].lower()
    return ".bin"


def media_type_for(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".json"):
        return MEDIA_TYPE_JSON
    if lowered.endswith(".svg"):
        return MEDIA_TYPE_SVG
    return DEFAULT_ASSET_MEDIA_TYPE


__all__ = [
    "ASSET_DIRECTORY",
    "DEFAULT_ASSET_MEDIA_TYPE",
    "LESSON_PLAN_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_VERSION",
    "MEDIA_TYPE_JSON",
    "MEDIA_TYPE_SVG",
    "SCENE_DIRECTORY",
    "SOURCE_DOCUMENT_EXTENSIONS",
    "UNINDEXED",
    "asset_path",
    "extension_of",
    "lesson_plan_path",
    "media_type_for",
    "package_prefix",
    "scene_path",
]
