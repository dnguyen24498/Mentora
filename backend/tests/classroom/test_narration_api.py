"""The teacher's narration stream over HTTP (V0-013)."""

from __future__ import annotations

import json

from tests.test_teacher_assigns_and_student_joins import (  # noqa: F401 - fixtures
    _class_for,
    _enrol,
    _student,
    _teacher,
    client,
    settings,
)


def _lines(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_teacher_streams_narration_and_student_is_refused(client):
    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)

    before = client.get(f"/classes/{class_id}/narration/0", headers=teacher)
    assert before.status_code == 409
    assert before.json()["error"]["issue_code"] == "NOT_STARTED"

    started = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert started.status_code == 200, started.text
    version = started.json()["session"]["state_version"]

    response = client.get(
        f"/classes/{class_id}/narration/0",
        params={"expected_state_version": version},
        headers=teacher,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-store"
    events = _lines(response)
    assert events[0]["type"] == "narration.started"
    assert events[0]["provider"]["name"] == "neutral-deterministic"
    assert events[-1]["type"] == "narration.completed"
    assert events[-1]["status"] in {"COMPLETED", "EMPTY"}

    stale = client.get(
        f"/classes/{class_id}/narration/0",
        params={"expected_state_version": version + 7},
        headers=teacher,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["issue_code"] == "STALE_STATE_VERSION"

    assert client.get(f"/classes/{class_id}/narration/999", headers=teacher).status_code == 404

    _enrol(client, teacher, class_id, student)
    refused = client.get(f"/classes/{class_id}/narration/0", headers=student)
    assert refused.status_code == 403

    assert client.post(f"/classes/{class_id}/end", headers=teacher).status_code == 200
    ended = client.get(f"/classes/{class_id}/narration/0", headers=teacher)
    assert ended.status_code == 409
    assert ended.json()["error"]["issue_code"] == "CLASS_ENDED"
