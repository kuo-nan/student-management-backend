
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Dept, Student
from schemas import StudentCrate, StudentUpdate
from utils import paginate


def get_student_page(
    db: Session,
    page: int,
    page_size: int,
    student_no: str | None = None,
    name: str | None = None,
):
    query = (
        select(
            Student.student_no,
            Student.id,
            Student.name,
            Student.age,
            Student.score,
            Student.dept_id,
            Dept.dept_name,
        )
        .join(Dept, Student.dept_id == Dept.id, isouter=True)
        .order_by(Student.id.desc())
    )
    if student_no:
        query = query.where(Student.student_no == student_no)
    if name:
        query = query.where(Student.name.like(f"%{name}%"))
    return paginate(db, query, page, page_size)


def create_student(db: Session, data: StudentCrate):
    student = Student(**data.model_dump())
    db.add(student)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "student_no" in str(exc.orig).lower():
            raise ValueError("学号已存在") from None
        raise
    db.refresh(student)
    return student


def update_student_service(
    db: Session,
    student_id: int,
    data: StudentUpdate,
):
    student = db.get(Student, student_id)
    if not student:
        raise ValueError("学生不存在")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(student, key, value)
    db.commit()
    db.refresh(student)
    return student
