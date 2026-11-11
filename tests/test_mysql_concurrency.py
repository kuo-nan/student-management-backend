import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Course, Dept, Student, StudentLeave
from schemas import LeaveAudit, StudentCreate
from services.leave_service import audit_leave, cancel_leave
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
        db.add(
            Student(
                student_no=1,
                id=1,
                name="并发测试学生",
                age=20,
                personal_score=90,
            )
        )
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
                        personal_score=90,
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


def test_concurrent_leave_audit_and_cancel_only_allows_one_winner(
    mysql_session_factory,
):
    with mysql_session_factory() as db:
        db.add(
            Student(
                student_no=1001,
                id=1001,
                name="撤销并发测试学生",
                age=20,
                personal_score=90,
            )
        )
        db.add(
            StudentLeave(
                id=1001,
                student_id=1001,
                leave_type="病假",
                start_time=datetime(2026, 12, 2, 8, 0, 0),
                end_time=datetime(2026, 12, 2, 18, 0, 0),
                reason="撤销与审批并发测试",
                status="pending",
            )
        )
        db.commit()

    barrier = Barrier(2)

    def audit_attempt() -> str:
        with mysql_session_factory() as db:
            barrier.wait(timeout=5)
            try:
                audit_leave(
                    db,
                    leave_id=1001,
                    data=LeaveAudit(
                        status="approved",
                        audit_remark="并发审批",
                    ),
                )
                return "success"
            except ValueError:
                return "conflict"

    def cancel_attempt() -> str:
        with mysql_session_factory() as db:
            barrier.wait(timeout=5)
            try:
                cancel_leave(db, leave_id=1001, student_id=1001)
                return "success"
            except ValueError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        audit_future = executor.submit(audit_attempt)
        cancel_future = executor.submit(cancel_attempt)
        audit_result = audit_future.result(timeout=10)
        cancel_result = cancel_future.result(timeout=10)

    assert sorted([audit_result, cancel_result]) == ["conflict", "success"]

    with mysql_session_factory() as db:
        saved = db.get(StudentLeave, 1001)
        if audit_result == "success":
            assert saved is not None
            assert saved.status == "approved"
        else:
            assert saved is None


def test_concurrent_course_and_dept_names_only_allow_one_winner(
    mysql_session_factory,
):
    dept_barrier = Barrier(2)

    def create_dept() -> str:
        with mysql_session_factory() as db:
            dept_barrier.wait(timeout=5)
            try:
                db.add(Dept(dept_name="并发唯一班级"))
                db.commit()
                return "success"
            except IntegrityError:
                db.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        dept_results = list(executor.map(lambda _: create_dept(), range(2)))

    assert sorted(dept_results) == ["conflict", "success"]

    course_barrier = Barrier(2)

    def create_course() -> str:
        with mysql_session_factory() as db:
            course_barrier.wait(timeout=5)
            try:
                db.add(Course(course_name="并发唯一课程", credits=3))
                db.commit()
                return "success"
            except IntegrityError:
                db.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        course_results = list(executor.map(lambda _: create_course(), range(2)))

    assert sorted(course_results) == ["conflict", "success"]

    with mysql_session_factory() as db:
        dept_count = db.scalar(
            select(func.count())
            .select_from(Dept)
            .where(Dept.dept_name == "并发唯一班级")
        )
        course_count = db.scalar(
            select(func.count())
            .select_from(Course)
            .where(Course.course_name == "并发唯一课程")
        )
        assert dept_count == 1
        assert course_count == 1
