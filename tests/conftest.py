import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DEBUG"] = "false"
os.environ["JWT_SECRET"] = "test-secret-key-for-tests-only"

from constants import UserRole  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from models import Course, Dept, Student, User, student_course  # noqa: E402
from utils import hash_password  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        dept = Dept(id=1, dept_name="计算机科学与技术")
        course = Course(id=1, course_name="Python 后端开发", credits=3)
        course_two = Course(id=2, course_name="数据库原理", credits=3)
        student = Student(id=1, name="张三", age=20, score=88, dept_id=1)
        unlinked_student = Student(
            id=2,
            name="李四",
            age=20,
            score=80,
            dept_id=1,
        )
        admin = User(
            id=10,
            username="admin",
            password_hash=hash_password("admin12345"),
            role=UserRole.ADMIN.value,
        )
        student_user = User(
            id=11,
            username="student",
            password_hash=hash_password("student12345"),
            role=UserRole.STUDENT.value,
            student=student,
        )
        db.add_all(
            [
                dept,
                course,
                course_two,
                unlinked_student,
                admin,
                student_user,
            ]
        )
        db.flush()
        db.execute(
            insert(student_course).values(student_id=1, course_id=1)
        )
        db.commit()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client: TestClient):
    return login(client, "admin", "admin12345")


@pytest.fixture()
def student_headers(client: TestClient):
    return login(client, "student", "student12345")
