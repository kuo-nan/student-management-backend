from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Dept, Student
from schemas import StudentCrate, StudentUpdate
from utils import paginate


def get_student_page(
    db: Session,
    page: int,
    page_size: int,
    name: str | None = None,
):
    query = (
        select(
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
    if name:
        query = query.where(Student.name.like(f"%{name}%"))
    return paginate(db, query, page, page_size)


def create_student(db: Session, data: StudentCrate):
    db_student = Student(**data.model_dump())
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student


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
