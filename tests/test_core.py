from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_student_list_requires_login(client: TestClient):
    response = client.get("/student/list")

    assert response.status_code == 401


def test_student_cannot_access_admin_endpoint(
    client: TestClient,
    student_headers: dict[str, str],
):
    response = client.get("/student/list", headers=student_headers)

    assert response.status_code == 403


def test_admin_student_list_returns_joined_fields(
    client: TestClient,
    admin_headers: dict[str, str],
):
    response = client.get("/student/list", headers=admin_headers)

    assert response.status_code == 200, response.text
    items = response.json()["data"]["list"]
    item = next(item for item in items if item["name"] == "张三")
    assert item["dept_name"] == "计算机科学与技术"


def test_update_student_does_not_recurse(
    client: TestClient,
    admin_headers: dict[str, str],
):
    response = client.put(
        "/student/update_student/1",
        json={"score": 91},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["score"] == 91


def test_student_cannot_create_exam(
    client: TestClient,
    student_headers: dict[str, str],
):
    response = client.post(
        "/exam",
        json={"name": "期末考试", "exam_time": "2027-01-05T09:00:00"},
        headers=student_headers,
    )

    assert response.status_code == 403


def test_exam_name_is_unique(
    client: TestClient,
    admin_headers: dict[str, str],
):
    payload = {"name": "阶段考试", "exam_time": "2026-12-10T09:00:00"}
    first = client.post("/exam", json=payload, headers=admin_headers)
    second = client.post("/exam", json=payload, headers=admin_headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 400


def test_student_leave_uses_linked_student_identity(
    client: TestClient,
    student_headers: dict[str, str],
):
    response = client.post(
        "/leave",
        json={
            "leave_type": "病假",
            "start_time": "2026-12-01T08:00:00",
            "end_time": "2026-12-02T18:00:00",
            "reason": "发烧就医",
        },
        headers=student_headers,
    )
    records = client.get("/leave/my", headers=student_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["student_id"] == 1
    assert records.status_code == 200, records.text
    assert records.json()["data"]["total"] == 1


def test_score_requires_course_enrollment(
    client: TestClient,
    admin_headers: dict[str, str],
):
    exam = client.post(
        "/exam",
        json={"name": "选课校验考试", "exam_time": "2026-12-20T09:00:00"},
        headers=admin_headers,
    )
    exam_id = exam.json()["data"]["id"]

    enrolled = client.post(
        "/exam/score",
        json={
            "exam_id": exam_id,
            "student_id": 1,
            "course_id": 1,
            "exam_score": 95,
        },
        headers=admin_headers,
    )
    not_enrolled = client.post(
        "/exam/score",
        json={
            "exam_id": exam_id,
            "student_id": 1,
            "course_id": 2,
            "exam_score": 90,
        },
        headers=admin_headers,
    )

    assert enrolled.status_code == 200, enrolled.text
    assert not_enrolled.status_code == 400
    assert "未选择" in not_enrolled.json()["message"]


def test_admin_can_create_linked_student_account(
    client: TestClient,
    admin_headers: dict[str, str],
):
    response = client.post(
        "/auth/user/student_account",
        json={
            "username": "student2",
            "password": "student23456",
            "student_id": 2,
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["role"] == "student"
