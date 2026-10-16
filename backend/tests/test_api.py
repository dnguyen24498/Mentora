import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.fixtures import simple_pptx

PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
HEADERS = {"X-Institution-Id": "inst-1"}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _create_course(client, title: str = "Intro to AI") -> str:
    response = client.post("/courses", params={"title": title}, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["course_id"]


def _upload(client, course_id: str, data: bytes, headers=HEADERS):
    return client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("deck.pptx", data, PPTX_MEDIA_TYPE)},
        headers=headers,
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_then_extract(client):
    course_id = _create_course(client)
    response = _upload(client, course_id, simple_pptx("Attention is all you need"))
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["created"] is True
    assert body["job_status"] == "PENDING"

    extracted = client.post(f"/artifacts/{body['artifact_id']}/extract", headers=HEADERS)
    assert extracted.status_code == 200, extracted.text
    document = extracted.json()
    assert document["slide_count"] == 1
    assert document["slides"][0]["scene_id"] == "ppt/slides/slide1.xml"


def test_duplicate_upload_reports_not_created(client):
    course_id = _create_course(client)
    deck = simple_pptx()
    first = _upload(client, course_id, deck).json()
    second = _upload(client, course_id, deck).json()
    assert second["created"] is False
    assert second["artifact_id"] == first["artifact_id"]


def test_missing_tenant_header_is_rejected(client):
    response = client.post("/courses", params={"title": "x"})
    assert response.status_code in (400, 422)


def test_cross_tenant_upload_is_forbidden(client):
    course_id = _create_course(client)
    response = _upload(client, course_id, simple_pptx(), headers={"X-Institution-Id": "inst-2"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


def test_invalid_file_returns_stable_code(client):
    course_id = _create_course(client)
    response = _upload(client, course_id, b"definitely not a pptx")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_TYPE"


def test_unknown_artifact_is_not_found(client):
    response = client.get("/artifacts/does-not-exist", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_list_courses_is_tenant_scoped(client):
    _create_course(client, "Alpha")
    own = client.get("/courses", headers=HEADERS).json()
    assert [course["title"] for course in own] == ["Alpha"]
    other = client.get("/courses", headers={"X-Institution-Id": "inst-2"}).json()
    assert other == []


def test_list_materials_returns_uploaded_files_newest_first(client):
    course_id = _create_course(client)
    first = _upload(client, course_id, simple_pptx("first")).json()
    second = _upload(client, course_id, simple_pptx("second")).json()

    response = client.get(f"/courses/{course_id}/materials", headers=HEADERS)
    assert response.status_code == 200, response.text
    materials = response.json()
    assert [material["artifact_id"] for material in materials] == [
        second["artifact_id"],
        first["artifact_id"],
    ]

    newest = materials[0]
    assert newest["filename"] == "deck.pptx"
    assert newest["job_status"] == "PENDING"
    assert newest["version"] == 2
    assert newest["byte_size"] > 0
    assert newest["sha256"]
    assert set(newest) >= {
        "artifact_id",
        "version_id",
        "version",
        "filename",
        "media_type",
        "sha256",
        "byte_size",
        "created_at",
        "job_id",
        "job_status",
    }


def test_list_materials_reflects_extraction_status(client):
    course_id = _create_course(client)
    artifact_id = _upload(client, course_id, simple_pptx("deck")).json()["artifact_id"]
    client.post(f"/artifacts/{artifact_id}/extract", headers=HEADERS)

    materials = client.get(f"/courses/{course_id}/materials", headers=HEADERS).json()
    assert materials[0]["job_status"] == "EXTRACTED"


def test_list_materials_dedupes_repeat_uploads(client):
    course_id = _create_course(client)
    deck = simple_pptx("only-once")
    _upload(client, course_id, deck)
    _upload(client, course_id, deck)

    materials = client.get(f"/courses/{course_id}/materials", headers=HEADERS).json()
    assert len(materials) == 1


def test_list_materials_is_tenant_scoped(client):
    course_id = _create_course(client)
    _upload(client, course_id, simple_pptx())

    other = client.get(f"/courses/{course_id}/materials", headers={"X-Institution-Id": "inst-2"})
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


def test_list_materials_unknown_course_is_not_found(client):
    response = client.get("/courses/does-not-exist/materials", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
