from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Course, Exam, ExamScore, Student, student_course
from schemas import ExamCreate, ExamUpdate, ScoreCreate, ScoreUpdate
from utils import paginate


def create_exam(db: Session, data: ExamCreate):
    if db.scalar(select(Exam.id).where(Exam.name == data.name)):
        raise ValueError("考试名称已存在")

    db_exam = Exam(**data.model_dump())
    db.add(db_exam)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("考试名称已存在") from None
    db.refresh(db_exam)
    return db_exam


def get_exam_page(
    db: Session,
    page: int,
    page_size: int,
    name: str | None = None,
):
    query = select(Exam).order_by(Exam.exam_time.desc())
    if name:
        query = query.where(Exam.name.like(f"%{name}%"))
    return paginate(db, query, page, page_size)


def update_exam(db: Session, exam_id: int, data: ExamUpdate):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise ValueError("考试不存在")
    updates = data.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] != exam.name:
        duplicate = db.scalar(
            select(Exam.id).where(
                Exam.name == updates["name"],
                Exam.id != exam_id,
            )
        )
        if duplicate:
            raise ValueError("考试名称已存在")
    for key, value in updates.items():
        setattr(exam, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("考试名称已存在") from None
    db.refresh(exam)
    return exam


def delete_exam(db: Session, exam_id: int):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise ValueError("考试不存在")
    score_count = db.scalar(
        select(func.count())
        .select_from(ExamScore)
        .where(ExamScore.exam_id == exam_id)
    )
    if score_count:
        raise ValueError("该考试已有成绩，无法删除")
    db.delete(exam)
    db.commit()


def create_score(db: Session, data: ScoreCreate):
    if not db.get(Exam, data.exam_id):
        raise ValueError("考试不存在")
    if not db.get(Student, data.student_id):
        raise ValueError("学生不存在")
    if not db.get(Course, data.course_id):
        raise ValueError("课程不存在")
    enrolled = db.scalar(
        select(student_course.c.student_id).where(
            student_course.c.student_id == data.student_id,
            student_course.c.course_id == data.course_id,
        )
    )
    if enrolled is None:
        raise ValueError("该学生未选择此课程，不能录入成绩")

    db_score = ExamScore(**data.model_dump())
    db.add(db_score)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("该学生本次考试该课程已有成绩，请修改而非重复录入") from None
    db.refresh(db_score)
    return db_score


def get_score_page(
    db: Session,
    page: int,
    page_size: int,
    exam_id: int | None = None,
    student_id: int | None = None,
    course_id: int | None = None,
):
    query = select(ExamScore).order_by(ExamScore.create_time.desc())
    if exam_id:
        query = query.where(ExamScore.exam_id == exam_id)
    if student_id:
        query = query.where(ExamScore.student_id == student_id)
    if course_id:
        query = query.where(ExamScore.course_id == course_id)
    return paginate(db, query, page, page_size)


def update_score(db: Session, score_id: int, data: ScoreUpdate):
    score = db.get(ExamScore, score_id)
    if not score:
        raise ValueError("成绩记录不存在")
    score.exam_score = data.exam_score
    db.commit()
    db.refresh(score)
    return score


def get_my_score(
    db: Session,
    student_id: int,
    page: int,
    page_size: int,
):
    query = (
        select(ExamScore)
        .where(ExamScore.student_id == student_id)
        .order_by(ExamScore.create_time.desc())
    )
    return paginate(db, query, page, page_size)
