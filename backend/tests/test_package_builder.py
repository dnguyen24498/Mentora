"""V0-006 baseline package builder: contracts, integrity, and the stage service.

The contract checks in this module are driven by the *real* schema files under
``contracts/ctf/`` — a small dependency-free evaluator for the JSON-Schema
keywords those three documents actually use (``jsonschema`` is not installed, and
adding a production dependency is not allowed; FND-003 formalises schema checks
with a dev-only dependency).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.common.errors import PublicationBlockedError, TenantAccessError
from app.compiler.models.ir import ContentIRDocument
from app.compiler.package_builder import (
    BUILDING_BASELINE_STAGE,
    BaselinePackage,
    PackageBuildError,
    PackageBuildService,
    PackageBuilder,
    PackageFile,
    PackageMetadata,
    content_package_version,
    lesson_plan_version_for,
)
from app.compiler.package_builder.layout import MANIFEST_FILENAME
from app.compiler.render_service import RenderingService
from app.compiler.renderers.structural import StructuralSvgRenderer
from app.compiler.renderers.testing import FakeRenderer
from app.compiler.validators.package import (
    MANIFEST_REQUIRED_FIELDS,
    assert_package_ok,
    validate_package,
)
from tests.fixtures import build_pptx, picture_shape, text_shape

REPO_ROOT = Path(__file__).resolve().parents[2]
CTF_CONTRACTS = REPO_ROOT / "contracts" / "ctf"

CREATED_AT = "2026-01-01T00:00:00+00:00"
PACKAGE_ID = "pkg-fixed-0001"
SCENE_PATH = "scenes/000-ppt-slides-slide1-xml.json"
LESSON_PLAN_PATH = "lesson-plan.json"
ASSET_PATH = "assets/cf635917c8911e9d57ea9e05a9b92f5cdcbf5742d7a335625ca95b71d7a7e743.svg"


# -- a dependency-free JSON-Schema subset evaluator --------------------------------
def _type_ok(value, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise AssertionError(f"unsupported schema type {expected!r}")


_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _validate(schema: dict, instance, path: str = "$") -> list[str]:
    """Evaluate the keywords used by ``contracts/ctf/*.schema.json``."""

    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(instance, t) for t in allowed):
            return [f"{path}: expected {expected}, got {type(instance).__name__}"]

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: {instance} <= exclusiveMinimum {schema['exclusiveMinimum']}")
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
        if schema.get("format") == "date-time" and not _DATETIME.match(instance):
            errors.append(f"{path}: {instance!r} is not a date-time")

    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        properties = schema.get("properties", {})
        for name, value in instance.items():
            if name in properties:
                errors.extend(_validate(properties[name], value, f"{path}.{name}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property {name!r}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(_validate(schema["items"], item, f"{path}[{index}]"))
    return errors


def load_schema(name: str) -> dict:
    return json.loads((CTF_CONTRACTS / name).read_text(encoding="utf-8"))


def assert_matches_schema(name: str, instance) -> None:
    errors = _validate(load_schema(name), instance)
    assert errors == [], f"{name} violation: {errors}"


# -- helpers ----------------------------------------------------------------------
def parse(package: BaselinePackage, path: str):
    return json.loads(package.file(path).data.decode("utf-8"))


def rewrite_json(package: BaselinePackage, path: str, mutate) -> BaselinePackage:
    """Rewrite one JSON document and re-checksum it, isolating the check under test."""

    document = parse(package, path)
    mutate(document)
    data = json.dumps(document, sort_keys=True, indent=2).encode("utf-8")
    files = [
        PackageFile(f.path, f.media_type, data) if f.path == path else f for f in package.files
    ]
    manifest = dict(package.manifest)
    manifest["files"] = [
        {**entry, "sha256": hashlib.sha256(data).hexdigest()} if entry["path"] == path else entry
        for entry in manifest["files"]
    ]
    return BaselinePackage(manifest=manifest, files=tuple(files))


def assets_for(rendered, object_store) -> dict[str, bytes]:
    """Every asset the rendered document references, read from the store."""

    return {
        scene.fallback_asset: object_store.get(scene.fallback_asset)
        for scene in rendered.document.slides
        if scene.fallback_asset
    }


def build_from(compiled, metadata: PackageMetadata, object_store) -> BaselinePackage:
    return PackageBuilder().build(
        compiled.document, metadata=metadata, assets=assets_for(compiled, object_store)
    )


# -- fixtures ---------------------------------------------------------------------
@pytest.fixture
def rendered(stored_artifact, rendering_service):
    """The real extract -> render pipeline result for the one-slide fixture."""

    artifact, _course = stored_artifact
    return rendering_service.compile("inst-1", artifact.artifact_id)


@pytest.fixture
def builder() -> PackageBuilder:
    return PackageBuilder()


@pytest.fixture
def metadata() -> PackageMetadata:
    return PackageMetadata(
        tenant_id="inst-1",
        course_id="course-1",
        course_version="1",
        content_package_version="cpv-0123456789abcdef",
        lesson_plan_version="lp-0123456789abcdef",
        lesson_id="baseline:course-1",
        package_id=PACKAGE_ID,
        created_at=CREATED_AT,
        knowledge_index_version="unindexed",
        compiler_version="1.1.0",
        source_sha256="0" * 64,
    )


@pytest.fixture
def package(rendered, builder, metadata, object_store) -> BaselinePackage:
    return builder.build(
        rendered.document, metadata=metadata, assets=assets_for(rendered, object_store)
    )


@pytest.fixture
def service(repository, object_store, rendering_service) -> PackageBuildService:
    return PackageBuildService(repository, object_store, rendering_service)


@pytest.fixture
def rendered_from_pptx(repository, object_store, extractor, upload_service, course, render_config):
    """Compile an arbitrary deck through the real pipeline."""

    def _compile(data: bytes, filename: str = "deck.pptx"):
        artifact = upload_service.upload(
            institution_id="inst-1", course_id=course.course_id, filename=filename, data=data
        ).artifact
        service = RenderingService(
            repository,
            object_store,
            extractor,
            StructuralSvgRenderer(object_store, render_config),
            config=render_config,
        )
        return service.compile("inst-1", artifact.artifact_id)

    return _compile


# -- golden package ---------------------------------------------------------------
def test_golden_package_layout(package):
    assert package.paths() == (ASSET_PATH, LESSON_PLAN_PATH, SCENE_PATH)
    assert package.package_id == PACKAGE_ID


def test_golden_manifest_matches_the_contract(package):
    assert_matches_schema("manifest.schema.json", package.manifest)
    assert set(package.manifest) == set(MANIFEST_REQUIRED_FIELDS) | {"teaching_graph_version"}
    assert package.manifest["schema_version"] == "1.0.0"
    assert package.manifest["course_version"] == "1"
    assert package.manifest["lesson_plan_versions"] == ["lp-0123456789abcdef"]


def test_golden_documents_match_their_contracts(package):
    assert_matches_schema("lesson-plan.schema.json", parse(package, LESSON_PLAN_PATH))
    assert_matches_schema("scene.schema.json", parse(package, SCENE_PATH))


def test_build_is_byte_stable_for_the_same_inputs(rendered, builder, metadata, object_store):
    assets = assets_for(rendered, object_store)
    first = builder.build(rendered.document, metadata=metadata, assets=assets)
    second = builder.build(rendered.document, metadata=metadata, assets=assets)

    assert first.manifest_bytes == second.manifest_bytes
    assert [(f.path, f.sha256) for f in first.files] == [(f.path, f.sha256) for f in second.files]


def test_manifest_lists_files_sorted_by_path(package):
    paths = [entry["path"] for entry in package.manifest["files"]]
    assert paths == sorted(paths)
    assert package.paths() == tuple(paths)


# -- manifest / envelope invariants ------------------------------------------------
def test_manifest_is_the_commit_point_and_never_lists_itself(package):
    listed = [entry["path"] for entry in package.manifest["files"]]
    assert MANIFEST_FILENAME not in listed
    assert package.manifest_file.path == MANIFEST_FILENAME


def test_manifest_files_carry_checksums_and_media_types(package):
    for entry in package.manifest["files"]:
        assert re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
        assert package.file(entry["path"]).sha256 == entry["sha256"]
        assert entry["media_type"] in {"application/json", "image/svg+xml"}


def test_manifest_rejects_unknown_fields(package):
    manifest = dict(package.manifest)
    manifest["publish_state"] = "REVIEW_REQUIRED"
    report = validate_package(BaselinePackage(manifest=manifest, files=package.files))

    assert report.ok is False
    assert any(i.code == "UNKNOWN_MANIFEST_FIELD" for i in report.errors)
    assert load_schema("manifest.schema.json")["additionalProperties"] is False


def test_manifest_rejects_a_wrong_schema_version(package):
    manifest = dict(package.manifest, schema_version="2.0.0")
    report = validate_package(BaselinePackage(manifest=manifest, files=package.files))
    assert any(i.code == "INVALID_MANIFEST_SCHEMA_VERSION" for i in report.errors)


def test_manifest_requires_a_knowledge_index_version(package):
    manifest = dict(package.manifest)
    del manifest["knowledge_index_version"]
    report = validate_package(BaselinePackage(manifest=manifest, files=package.files))
    assert any(i.code == "MISSING_MANIFEST_FIELD" for i in report.errors)


# -- references and self-containment ----------------------------------------------
def test_scene_fallback_asset_is_package_relative(package):
    reference = parse(package, SCENE_PATH)["fallback_asset"]

    assert reference == ASSET_PATH
    assert reference in [e["path"] for e in package.manifest["files"]]


def test_package_carries_no_source_document_and_no_zip_bytes(package):
    for package_file in package.files:
        assert not package_file.path.lower().endswith((".pptx", ".ppt", ".ppsx", ".odp"))
        assert not package_file.data.startswith(b"PK\x03\x04"), "no zip/OOXML container"
        assert b"<p:sld" not in package_file.data, "no source XML markup"


def test_package_builder_has_no_source_parser_dependency():
    """The built package cannot require an OOXML parser (DEC-CONTENT-001)."""

    import app.compiler.package_builder as module

    module_dir = Path(module.__file__).parent
    sources = sorted(module_dir.glob("*.py"))
    assert sources, "sanity: the package builder package must exist"
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for forbidden in ("zipfile", "xml.etree", "app.compiler.extractors"):
            assert forbidden not in text, f"{source.name} depends on {forbidden}"


# -- scenes, steps, and the lesson plan -------------------------------------------
def test_steps_reveal_every_object_in_reading_order(package):
    document = parse(package, SCENE_PATH)
    steps = document["steps"]

    assert len(steps) == 1, "V0-004 extracts no animation timing, so the baseline is one step"
    assert steps[0]["kind"] == "ALL_VISIBLE"
    reading_order = [
        obj["source_id"] for obj in sorted(document["objects"], key=lambda o: o["reading_order"])
    ]
    assert steps[0]["object_ids"] == reading_order
    assert len(reading_order) == len(document["objects"])


def test_lesson_plan_has_one_section_per_scene_in_order(package):
    plan = parse(package, LESSON_PLAN_PATH)
    scene_id = parse(package, SCENE_PATH)["scene_id"]

    assert plan["lesson_id"] == "baseline:course-1"
    section = plan["sections"][0]
    assert len(plan["sections"]) == 1
    assert section["scene_id"] == scene_id
    assert section["type"] == "EXPLANATION"
    assert section["safe_markers"] == [f"{scene_id}#step-0"]
    assert section["scene_step_id"] == f"{scene_id}#step-0"


def test_lesson_plan_carries_speaker_notes_verbatim(rendered_from_pptx, metadata, object_store):
    deck = build_pptx([[text_shape(2, "T", text="Title")]], notes={1: "Explain the invariant."})
    compiled = rendered_from_pptx(deck)
    plan = parse(build_from(compiled, metadata, object_store), LESSON_PLAN_PATH)

    assert plan["sections"][0]["script"] == "Explain the invariant."


def test_media_only_scene_becomes_a_media_section(rendered_from_pptx, metadata, object_store):
    compiled = rendered_from_pptx(build_pptx([[picture_shape(2, "Picture 1")]]), "img.pptx")
    plan = parse(build_from(compiled, metadata, object_store), LESSON_PLAN_PATH)

    assert plan["sections"][0]["type"] == "MEDIA"
    assert plan["sections"][0]["script"] is None


def test_multiple_scenes_keep_deck_order(rendered_from_pptx, metadata, object_store):
    deck = build_pptx(
        [[text_shape(2, "A", text="one")], [text_shape(2, "B", text="two")]]
    )
    built = build_from(rendered_from_pptx(deck), metadata, object_store)
    plan = parse(built, LESSON_PLAN_PATH)

    assert [s["section_id"] for s in plan["sections"]] == [
        "baseline:course-1#section-0",
        "baseline:course-1#section-1",
    ]
    scene_paths = [p for p in built.paths() if p.startswith("scenes/")]
    assert scene_paths == ["scenes/000-ppt-slides-slide1-xml.json", "scenes/001-ppt-slides-slide2-xml.json"]


# -- no Teaching Graph, no index ---------------------------------------------------
def test_no_teaching_graph_and_unindexed_by_default(package):
    assert package.manifest["teaching_graph_version"] is None
    assert package.manifest["knowledge_index_version"] == "unindexed"
    report = validate_package(package)
    assert report.ok is True
    assert report.requires_review is False


# -- required negative tests ------------------------------------------------------
def test_missing_asset_is_rejected_by_the_builder(rendered, metadata):
    with pytest.raises(PackageBuildError) as exc:
        PackageBuilder().build(rendered.document, metadata=metadata, assets={})
    assert exc.value.issue_code == "MISSING_ASSET"
    assert exc.value.http_status == 409


def test_asset_bytes_missing_from_the_package_are_rejected(package):
    kept = [f for f in package.files if not f.path.startswith("assets/")]
    report = validate_package(BaselinePackage(manifest=package.manifest, files=tuple(kept)))

    assert report.ok is False
    assert any(i.code == "MISSING_FILE_BYTES" for i in report.errors)


def test_manifest_without_the_scene_asset_is_an_invalid_reference(package):
    manifest = dict(package.manifest)
    manifest["files"] = [e for e in manifest["files"] if not e["path"].startswith("assets/")]
    report = validate_package(BaselinePackage(manifest=manifest, files=package.files))

    assert any(i.code == "MISSING_ASSET" for i in report.errors)


def test_compiler_asset_key_in_a_scene_is_an_invalid_ref(package):
    def mutate(document):
        document["fallback_asset"] = "renders/" + "a" * 64 + ".svg"

    report = validate_package(rewrite_json(package, SCENE_PATH, mutate))

    assert report.ok is False
    assert any(i.code == "INVALID_REF" and "compiler asset store" in i.message for i in report.errors)


def test_unknown_lesson_section_scene_is_an_invalid_ref(package):
    def mutate(plan):
        plan["sections"][0]["scene_id"] = "ppt/slides/slide99.xml"

    report = validate_package(rewrite_json(package, LESSON_PLAN_PATH, mutate))

    assert any(i.code == "INVALID_REF" and "unknown scene" in i.message for i in report.errors)


def test_safe_marker_that_is_not_a_step_is_an_invalid_ref(package):
    def mutate(plan):
        plan["sections"][0]["safe_markers"] = ["ppt/slides/slide1.xml#step-7"]

    report = validate_package(rewrite_json(package, LESSON_PLAN_PATH, mutate))

    assert any(i.code == "INVALID_REF" and "safe marker" in i.message for i in report.errors)


def test_step_referencing_an_unknown_object_is_an_invalid_ref(package):
    def mutate(document):
        document["steps"][0]["object_ids"] = ["ppt/slides/slide1.xml#999"]

    report = validate_package(rewrite_json(package, SCENE_PATH, mutate))

    assert any(i.code == "INVALID_REF" and "unknown object" in i.message for i in report.errors)


def test_checksum_mismatch_detects_mutation(package):
    target = package.file(SCENE_PATH)
    mutated = PackageFile(target.path, target.media_type, target.data + b"\n ")
    files = [mutated if f.path == target.path else f for f in package.files]

    report = validate_package(BaselinePackage(manifest=package.manifest, files=tuple(files)))
    assert report.ok is False
    assert any(i.code == "CHECKSUM_MISMATCH" for i in report.errors)

    with pytest.raises(PublicationBlockedError) as exc:
        assert_package_ok(report)
    assert exc.value.http_status == 409


def test_a_source_document_in_the_package_is_rejected(package):
    smuggled = PackageFile("deck.pptx", "application/octet-stream", b"PK\x03\x04source")
    manifest = dict(package.manifest)
    manifest["files"] = [*manifest["files"], smuggled.to_manifest_entry()]

    report = validate_package(BaselinePackage(manifest=manifest, files=(*package.files, smuggled)))
    assert any(i.code == "SOURCE_DOCUMENT_PRESENT" for i in report.errors)


def test_a_file_not_listed_in_the_manifest_is_rejected(package):
    orphan = PackageFile("scenes/999-orphan.json", "application/json", b"{}")
    report = validate_package(
        BaselinePackage(manifest=package.manifest, files=(*package.files, orphan))
    )
    assert any(i.code == "ORPHAN_FILE" for i in report.errors)


def test_degraded_fidelity_requires_review(rendered_from_pptx, metadata, object_store):
    compiled = rendered_from_pptx(
        build_pptx([[text_shape(2, "T", text="hi", font="Be Vietnam Pro")]]), "brand.pptx"
    )
    report = validate_package(
        build_from(compiled, metadata, object_store), render_validation=compiled.validation
    )

    assert report.ok is True, "degraded fidelity is reviewable, not invalid"
    assert report.requires_review is True
    assert any(
        i.code in {"DEGRADED_REQUIRES_REVIEW", "RENDER_REQUIRES_REVIEW"} for i in report.issues
    )


def test_render_gate_failure_blocks_packaging(package, rendered):
    blocked = replace(rendered.validation, ok=False, publishable=False)
    report = validate_package(package, render_validation=blocked)

    assert report.ok is False
    assert any(i.code == "RENDER_NOT_PUBLISHABLE" for i in report.errors)


def test_empty_document_is_rejected(builder, metadata):
    empty = ContentIRDocument(source_ref={}, slide_width=1, slide_height=1, slides=[])
    with pytest.raises(PackageBuildError) as exc:
        builder.build(empty, metadata=metadata, assets={})
    assert exc.value.issue_code == "NO_SCENES"


def test_unrendered_scene_is_rejected(builder, metadata, rendered):
    unrendered = replace(rendered.document.slides[0], fallback_asset=None)
    document = replace(rendered.document, slides=[unrendered])
    with pytest.raises(PackageBuildError) as exc:
        builder.build(document, metadata=metadata, assets={})
    assert exc.value.issue_code == "MISSING_FALLBACK_ASSET"


# -- versioning -------------------------------------------------------------------
def test_content_package_version_is_deterministic_and_config_sensitive():
    base = content_package_version("a" * 64, config_hash="cfg-1")
    assert base == content_package_version("a" * 64, config_hash="cfg-1")
    assert base != content_package_version("a" * 64, config_hash="cfg-2")
    assert base != content_package_version("b" * 64, config_hash="cfg-1")
    assert base != content_package_version("a" * 64, config_hash="cfg-1", compiler_version="9.9.9")
    assert lesson_plan_version_for(base) != lesson_plan_version_for("cpv-x")


# -- the stage service ------------------------------------------------------------
def test_service_builds_and_stores_a_self_contained_package(
    service, stored_artifact, object_store
):
    artifact, course = stored_artifact
    result = service.build("inst-1", artifact.artifact_id, created_at=CREATED_AT)

    assert result.stage == BUILDING_BASELINE_STAGE
    assert result.prefix == f"packages/{result.package.package_id}"
    assert result.validation.ok is True
    assert result.validation.requires_review is False
    manifest = result.package.manifest
    assert manifest["tenant_id"] == "inst-1"
    assert manifest["course_id"] == course.course_id
    assert manifest["course_version"] == "1"
    assert manifest["knowledge_index_version"] == "unindexed"
    assert manifest["teaching_graph_version"] is None
    assert manifest["created_at"] == CREATED_AT

    # Written last: the manifest is what makes the package discoverable.
    assert object_store.exists(f"{result.prefix}/{MANIFEST_FILENAME}")
    stored = json.loads(object_store.get(f"{result.prefix}/{MANIFEST_FILENAME}"))
    for entry in stored["files"]:
        data = object_store.get(f"{result.prefix}/{entry['path']}")
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]

    payload = result.to_dict()
    assert payload["job_status"] == "EXTRACTED"
    assert set(payload) == {
        "stage",
        "prefix",
        "package",
        "package_validation",
        "render_validation",
        "job_status",
    }


def test_stored_package_round_trips_through_the_contract_validator(
    service, stored_artifact, object_store
):
    artifact, _course = stored_artifact
    result = service.build("inst-1", artifact.artifact_id, created_at=CREATED_AT)
    prefix = result.prefix

    manifest = json.loads(object_store.get(f"{prefix}/{MANIFEST_FILENAME}"))
    files = tuple(
        PackageFile(
            entry["path"], entry["media_type"], object_store.get(f"{prefix}/{entry['path']}")
        )
        for entry in manifest["files"]
    )
    reloaded = BaselinePackage(manifest=manifest, files=files)

    assert reloaded.manifest_bytes == result.package.manifest_bytes
    assert validate_package(reloaded).ok is True
    assert_matches_schema("manifest.schema.json", reloaded.manifest)


def test_service_is_tenant_scoped(service, stored_artifact, repository, settings):
    artifact, _course = stored_artifact
    repository.ensure_institution("inst-2")

    with pytest.raises(TenantAccessError):
        service.build("inst-2", artifact.artifact_id)
    assert not (Path(settings.object_root) / "packages").exists()


def test_service_blocks_packaging_when_a_render_failed(
    repository, object_store, extractor, render_config, stored_artifact, settings
):
    artifact, _course = stored_artifact
    rendering = RenderingService(
        repository,
        object_store,
        extractor,
        FakeRenderer(object_store=object_store, fail_orders=(0,)),
        config=render_config,
    )
    service = PackageBuildService(repository, object_store, rendering)

    with pytest.raises(PublicationBlockedError):
        service.build("inst-1", artifact.artifact_id)
    assert not (Path(settings.object_root) / "packages").exists()


def test_service_rebuild_is_idempotent(service, stored_artifact, settings):
    artifact, _course = stored_artifact
    first = service.build("inst-1", artifact.artifact_id, created_at=CREATED_AT)
    second = service.build(
        "inst-1", artifact.artifact_id, created_at=CREATED_AT, package_id=first.package.package_id
    )

    assert first.package.manifest_bytes == second.package.manifest_bytes
    assert [(f.path, f.sha256) for f in first.package.files] == [
        (f.path, f.sha256) for f in second.package.files
    ]
    assert len(list((Path(settings.object_root) / "packages").iterdir())) == 1


def test_service_emits_structured_telemetry(service, stored_artifact, rendering_service):
    artifact, _course = stored_artifact
    records: list[dict] = []
    original = rendering_service.telemetry.emit

    def capture(event, **fields):
        record = original(event, **fields)
        records.append(record)
        return record

    rendering_service.telemetry.emit = capture  # type: ignore[method-assign]
    result = service.build("inst-1", artifact.artifact_id, created_at=CREATED_AT)

    built = [r for r in records if r["event"] == "compiler.package.built"]
    assert len(built) == 1
    record = built[0]
    assert record["package_id"] == result.package.package_id
    assert record["stage"] == BUILDING_BASELINE_STAGE
    assert record["scenes"] == 1
    assert record["files"] == 3
    assert record["knowledge_index_version"] == "unindexed"
    assert record["teaching_graph_version"] is None
    assert record["requires_review"] is False
    # Redaction: telemetry carries counts and identities, never slide text.
    assert "Hello world" not in json.dumps(record)


def test_content_version_binds_source_and_renderer_config(service, stored_artifact, object_store):
    artifact, _course = stored_artifact
    result = service.build("inst-1", artifact.artifact_id, created_at=CREATED_AT)
    identity = result.render.renderer

    expected = content_package_version(
        artifact.sha256, config_hash=identity.config_hash
    )
    assert result.package.manifest["content_package_version"] == expected
    assert result.package.manifest["lesson_plan_versions"] == [lesson_plan_version_for(expected)]
    plan = json.loads(object_store.get(f"{result.prefix}/{LESSON_PLAN_PATH}"))
    assert plan["lesson_plan_version"] == lesson_plan_version_for(expected)
    assert datetime.datetime.fromisoformat(result.package.manifest["created_at"])
