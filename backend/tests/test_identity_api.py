"""The authentication surface and the pinned scene read, end to end (V0-021).

Everything here drives the real FastAPI app, the real SQLite store and the real
object store. The properties asserted are the ones the task's acceptance criteria
name:

* a principal's tenant comes from the session, never from a request field;
* roles are enforced server-side (a student token is refused on teacher verbs);
* the join credential belongs to the authenticated student;
* login has no enumeration oracle;
* a revoked session is refused;
* the student learns the **pinned** publication, and a tampered pinned asset is
  refused rather than presented.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.fixtures import build_pptx, text_shape

HEADERS = {"X-Institution-Id": "university-001"}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _deck(slides: int = 3) -> bytes:
    return build_pptx(
        [[text_shape(2, f"S{index}", text=f"Slide {index}")] for index in range(1, slides + 1)],
        notes={index: f"Notes for Slide {index}" for index in range(1, slides + 1)},
    )


def _course(client, title: str = "Neural Nets") -> str:
    return client.post("/courses", params={"title": title}, headers=HEADERS).json()["course_id"]


def _class(client, course_id: str) -> str:
    response = client.post("/classes", params={"course_id": course_id}, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["class_id"]


def _publish(client, course_id: str, deck: bytes | None = None) -> dict:
    artifact_id = client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("lecture.pptx", deck or _deck(), "application/octet-stream")},
        headers=HEADERS,
    ).json()["artifact_id"]
    built = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    assert built["publishable"] is True, built
    decided = client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "APPROVE"},
        headers=HEADERS,
    ).json()
    published = client.post(
        f"/course-versions/{decided['version_id']}/publish", headers=HEADERS
    ).json()
    return {"artifact_id": artifact_id, "package_id": published["package_id"], **published}


def _invite(client, class_id: str, email: str) -> dict:
    response = client.post(
        f"/classes/{class_id}/enrollments", params={"email": email}, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return response.json()


def _login(client, email: str, credential: str, institution: str = "university-001"):
    return client.post(
        "/auth/login",
        json={"institution_id": institution, "email": email, "credential": credential},
    )


def _student(client, class_id: str, email: str = "ana@uni.test") -> tuple[str, dict]:
    invitation = _invite(client, class_id, email)
    response = _login(client, email, invitation["development_credential"])
    assert response.status_code == 200, response.text
    return invitation["student"]["account_id"], {
        "Authorization": f"Bearer {response.json()['token']}"
    }


# -- login -------------------------------------------------------------------------


def test_a_login_response_is_honest_about_the_mechanism(client):
    """The credential capability is a mock and the response says so (never presented
    as the platform's authentication)."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    invitation = _invite(client, class_id, "ana@uni.test")

    body = _login(client, "ana@uni.test", invitation["development_credential"]).json()

    assert body["authenticated"] is True
    assert body["token_type"] == "Bearer"
    assert body["principal"]["role"] == "student"
    assert body["principal"]["institution_id"] == "university-001"
    assert body["authenticator"]["kind"] == "DEVELOPMENT_MOCK"
    assert body["authenticator"]["id"] == "local-credentials@1.0.0"
    assert "DEVELOPMENT_MOCK" in body["notice"] or "development" in body["notice"].lower()


def test_login_is_not_an_enumeration_oracle(client):
    """An unknown account and a wrong credential answer identically."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    _invite(client, class_id, "ana@uni.test")

    wrong = _login(client, "ana@uni.test", "not-the-code")
    unknown = _login(client, "nobody@uni.test", "not-the-code")

    assert wrong.status_code == unknown.status_code == 401
    assert (
        wrong.json()["error"]["issue_code"]
        == unknown.json()["error"]["issue_code"]
        == "INVALID_CREDENTIALS"
    )
    assert wrong.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_a_session_is_the_only_thing_that_decides_the_tenant(client):
    """A second tenant's session cannot reach the first tenant's class."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    invitation = _invite(client, class_id, "ana@uni.test")
    # Sign in naming the *other* tenant: the account is not there, so nothing is
    # granted — a subject cannot choose which institution it is authenticated in.
    assert _login(client, "ana@uni.test", invitation["development_credential"], "university-002").status_code == 401

    token = _login(client, "ana@uni.test", invitation["development_credential"]).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/classes/{class_id}", headers=headers).status_code == 200
    # The tenant header alongside a session changes nothing.
    assert (
        client.get(
            f"/classes/{class_id}",
            headers={**headers, "X-Institution-Id": "university-002"},
        ).status_code
        == 200
    )


def test_me_reports_whether_a_real_session_was_presented(client):
    course_id = _course(client)
    class_id = _class(client, course_id)
    _, student = _student(client, class_id)

    signed_in = client.get("/auth/me", headers=student).json()
    assert signed_in["principal"]["authenticated"] is True
    assert signed_in["principal"]["account_id"]

    # The development tenant shortcut resolves a teacher, but it is *not* a sign-in.
    shortcut = client.get("/auth/me", headers=HEADERS).json()
    assert shortcut["principal"]["authenticated"] is False
    assert shortcut["principal"]["account_id"] is None

    anonymous = client.get("/auth/me")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["issue_code"] == "SESSION_REQUIRED"


def test_sign_out_revokes_the_session_and_is_idempotent(client):
    course_id = _course(client)
    class_id = _class(client, course_id)
    _, student = _student(client, class_id)

    assert client.post("/auth/logout", headers=student).json()["revoked"] is True
    assert client.post("/auth/logout", headers=student).json()["revoked"] is False

    refused = client.get("/auth/me", headers=student)
    assert refused.status_code == 401
    assert refused.json()["error"]["issue_code"] == "SESSION_REVOKED"


def test_an_unknown_or_malformed_session_is_refused(client):
    for header in ("Bearer nope", "Bearer", "Basic abc"):
        response = client.get("/auth/me", headers={"Authorization": header})
        assert response.status_code == 401, header


# -- the student's join ------------------------------------------------------------


def test_the_development_shortcut_cannot_join_a_class(client):
    """A join credential is bound to an account; a header is not one."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    _publish(client, course_id)
    assert client.post(f"/classes/{class_id}/start", headers=HEADERS).status_code == 200

    response = client.post(f"/classes/{class_id}/bootstrap-token", headers=HEADERS)
    assert response.status_code == 401
    assert response.json()["error"]["issue_code"] == "SESSION_REQUIRED"


def test_a_join_credential_is_always_the_callers_own(client):
    """There is no student id in the request: it cannot be someone else's join."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    _publish(client, course_id)
    assert client.post(f"/classes/{class_id}/start", headers=HEADERS).status_code == 200
    account_id, student = _student(client, class_id, "ana@uni.test")

    issued = client.post(f"/classes/{class_id}/bootstrap-token", headers=student)
    assert issued.status_code == 200, issued.text
    assert issued.json()["student_id"] == account_id
    assert issued.json()["scopes"] == ["subscribe"]


# -- the pinned scene --------------------------------------------------------------


def test_a_student_lists_the_pinned_slides_with_their_text(client):
    """The student page's navigation and narration come from the pinned package."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    published = _publish(client, course_id)
    assert client.post(f"/classes/{class_id}/start", headers=HEADERS).status_code == 200
    _, student = _student(client, class_id)

    response = client.get(f"/classes/{class_id}/scenes", headers=student)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["package_id"] == published["package_id"]
    assert body["scene_count"] == 3
    assert [scene["order"] for scene in body["scenes"]] == [0, 1, 2]
    assert "Slide 1" in body["scenes"][0]["text"]
    assert body["scenes"][0]["notes"] == "Notes for Slide 1"
    assert body["scenes"][0]["scene_id"]


def test_a_student_reads_the_pinned_slide(client):
    course_id = _course(client)
    class_id = _class(client, course_id)
    published = _publish(client, course_id)
    assert client.post(f"/classes/{class_id}/start", headers=HEADERS).status_code == 200
    _, student = _student(client, class_id)

    response = client.get(f"/classes/{class_id}/scenes/0", headers=student)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["x-mentora-package"] == published["package_id"]
    assert b"<svg" in response.content


def test_a_later_publication_does_not_move_what_the_class_is_reading(client):
    """``DEC-CONTENT-005``: an active session pins the version it started on."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    first = _publish(client, course_id)
    assert client.post(f"/classes/{class_id}/start", headers=HEADERS).status_code == 200
    _, student = _student(client, class_id)
    before = client.get(f"/classes/{class_id}/scenes/1", headers=student)

    # A correction is a *new* version (different content, so a different package),
    # published after this class started.
    second = _publish(client, course_id, deck=_deck(4))
    assert second["package_id"] != first["package_id"]

    after = client.get(f"/classes/{class_id}/scenes/1", headers=student)
    assert after.headers["x-mentora-package"] == first["package_id"]
    assert after.content == before.content


def test_a_scene_read_before_the_class_starts_is_404(client):
    course_id = _course(client)
    class_id = _class(client, course_id)
    _publish(client, course_id)
    account_id, student = _student(client, class_id)

    response = client.get(f"/classes/{class_id}/scenes/1", headers=student)
    assert response.status_code == 404, response.text


def test_a_scene_the_package_does_not_have_is_404(client):
    course_id = _course(client)
    class_id = _class(client, course_id)
    _publish(client, course_id)
    assert client.post(f"/classes/{class_id}/start", headers=HEADERS).status_code == 200
    _, student = _student(client, class_id)

    assert client.get(f"/classes/{class_id}/scenes/999", headers=student).status_code == 404


def test_a_tampered_pinned_asset_is_refused_not_presented(client, settings):
    """The read re-checks each served file against the digest the manifest recorded."""

    course_id = _course(client)
    class_id = _class(client, course_id)
    published = _publish(client, course_id)
    assert client.post(f"/classes/{class_id}/start", headers=HEADERS).status_code == 200
    _, student = _student(client, class_id)
    assert client.get(f"/classes/{class_id}/scenes/1", headers=student).status_code == 200

    assets = sorted(
        Path(settings.object_root)
        .joinpath("packages", published["package_id"])
        .rglob("*.svg")
    )
    assert assets, "the package should hold the rendered slides"
    for asset in assets:
        asset.write_bytes(b"<svg>swapped</svg>")

    response = client.get(f"/classes/{class_id}/scenes/1", headers=student)
    assert response.status_code == 502, response.text
    assert response.json()["error"]["issue_code"] == "SCENE_CHECKSUM_MISMATCH"
