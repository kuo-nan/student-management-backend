import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Dept, Student, StudentLeave
from schemas import LeaveAudit, StudentCreate
from services.leave_service import audit_leave
from services.student_service import create_student

pytestmark = pytest.mark.mysql


@pytest.fixture(scope="module")
def mysql_session_factory():
    database_url = os.getenv("MYSQL_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("MYSQL_TEST_DATABASE_URL is not configured")

    database_name = make_url(database_url).database or ""
    if "test" not in database_name.lower() and "verify" not in database_name.lower():
        pytest.fail("MYSQL_TEST_DATABASE_URL must point to a test or verify database")

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield session_factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_concurrent_leave_audit_only_allows_one_winner(mysql_session_factory):
    with mysql_session_factory() as db:
        db.add(Student(student_no=1,id=1, name="并发测试学生", age=20, score=90))
        db.add(
            StudentLeave(
                id=1,
                student_id=1,
                leave_type="事假",
                start_time=datetime(2026, 12, 1, 8, 0, 0),
                end_time=datetime(2026, 12, 1, 18, 0, 0),
                reason="并发审批测试",
                status="pending",
            )
        )
        db.commit()

    barrier = Barrier(2)

    def attempt(status: str) -> tuple[str, str | None]:
        with mysql_session_factory() as db:
            barrier.wait(timeout=5)
            try:
                audit_leave(
                    db,
                    leave_id=1,
                    data=LeaveAudit(
                        status=status,
                        audit_remark=f"管理员选择{status}",
                    ),
                )
                return "success", status
            except ValueError:
                return "conflict", status

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                attempt,
                ["approved", "rejected"],
            )
        )

    assert sorted(result[0] for result in results) == ["conflict", "success"]
    winner = next(result for result in results if result[0] == "success")

    with mysql_session_factory() as db:
        saved = db.scalar(select(StudentLeave).where(StudentLeave.id == 1))
        assert saved is not None
        assert saved.status == winner[1]
        assert saved.audit_remark == f"管理员选择{winner[1]}"


def test_concurrent_student_creation_only_allows_one_winner(
    mysql_session_factory,
):
    with mysql_session_factory() as db:
        db.add(Dept(id=1, dept_name="并发测试班级"))
        db.commit()

    barrier = Barrier(2)

    def attempt(name: str) -> str:
        with mysql_session_factory() as db:
            barrier.wait(timeout=5)
            try:
                create_student(
                    db,
                    StudentCreate(
                        student_no=20269999,
                        name=name,
                        age=20,
                        score=90,
                        dept_id=1,
                    ),
                )
                return "success"
            except ValueError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ["并发学生A", "并发学生B"]))

    assert sorted(results) == ["conflict", "success"]

    with mysql_session_factory() as db:
        count = db.scalar(
            select(func.count())
            .select_from(Student)
            .where(Student.student_no == 20269999)
        )
        assert count == 1
