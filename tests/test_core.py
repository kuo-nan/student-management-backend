from io import BytesIO

import openpyxl
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


def test_student_number_is_unique_and_filterable(
    client: TestClient,
    admin_headers: dict[str, str],
):
    payload = {
        "student_no": 20260001,
        "name": "王五",
        "age": 21,
        "score": 90,
        "dept_id": 1,
    }
    created = client.post(
        "/student/add_student",
        json=payload,
        headers=admin_headers,
    )
    duplicated = client.post(
        "/student/add_student",
        json=payload,
        headers=admin_headers,
    )
    filtered = client.get(
        "/student/list",
        params={"student_no": 20260001},
        headers=admin_headers,
    )

    assert created.status_code == 200, created.text
    assert created.json()["data"]["student_no"] == 20260001
    assert duplicated.status_code == 409
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["data"]["total"] == 1
    assert filtered.json()["data"]["list"][0]["student_no"] == 20260001


def test_student_excel_import_reports_duplicate_student_numbers(
    client: TestClient,
    admin_headers: dict[str, str],
):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["学号", "姓名", "年龄", "成绩", "班级ID"])
    sheet.append([20261001, "Excel学生A", 20, 91, 1])
    sheet.append([20261001, "文件内重复", 20, 90, 1])
    sheet.append([1, "数据库已有学号", 20, 89, 1])
    output = BytesIO()
    workbook.save(output)

    response = client.post(
        "/student/import_excel",
        files={
            "file": (
                "students.xlsx",
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["success_count"] == 1
    assert result["fail_count"] == 2
    assert any("文件内重复" in item or "学号已存在" in item for item in result["fail_detail"])


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
    leave_id = response.json()["data"]["id"]
    records = client.get("/leave/my", headers=student_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["student_id"] == 1
    assert records.status_code == 200, records.text
    assert any(item["id"] == leave_id for item in records.json()["data"]["list"])


def test_admin_can_approve_leave_with_remark(
    client: TestClient,
    admin_headers: dict[str, str],
    student_headers: dict[str, str],
):
    leave_id = _create_leave(client, student_headers, "审批通过测试")

    response = client.put(
        f"/leave/{leave_id}/audit",
        json={"status": "approved", "audit_remark": "材料完整，同意请假"},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "approved"
    assert response.json()["data"]["audit_remark"] == "材料完整，同意请假"


def test_admin_can_reject_leave(
    client: TestClient,
    admin_headers: dict[str, str],
    student_headers: dict[str, str],
):
    leave_id = _create_leave(client, student_headers, "审批驳回测试")

    response = client.put(
        f"/leave/{leave_id}/audit",
        json={"status": "rejected", "audit_remark": "请假理由不充分"},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "rejected"
    assert response.json()["data"]["audit_remark"] == "请假理由不充分"


def test_leave_cannot_be_audited_twice(
    client: TestClient,
    admin_headers: dict[str, str],
    student_headers: dict[str, str],
):
    leave_id = _create_leave(client, student_headers, "重复审批测试")
    first = client.put(
        f"/leave/{leave_id}/audit",
        json={"status": "approved", "audit_remark": "同意"},
        headers=admin_headers,
    )
    second = client.put(
        f"/leave/{leave_id}/audit",
        json={"status": "rejected", "audit_remark": "试图覆盖"},
        headers=admin_headers,
    )
    records = client.get(
        "/leave/list",
        params={"student_id": 1, "page_size": 100},
        headers=admin_headers,
    )
    saved = next(
        item for item in records.json()["data"]["list"] if item["id"] == leave_id
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 400
    assert saved["status"] == "approved"
    assert saved["audit_remark"] == "同意"


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


def _create_leave(
    client: TestClient,
    student_headers: dict[str, str],
    reason: str,
) -> int:
    response = client.post(
        "/leave",
        json={
            "leave_type": "事假",
            "start_time": "2026-12-10T08:00:00",
            "end_time": "2026-12-11T18:00:00",
            "reason": reason,
        },
        headers=student_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]
