import json
from typing import List

from fastapi import APIRouter, Depends
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db, redis_client
from models import Course, Dept, Student, Teacher, User, student_course, teacher_course
from schemas import DeptStatResp, ResponseModel, TeacherCourseStatResp
from utils import get_current_admin

router = APIRouter(prefix="/student", tags=["统计业务"])


@router.get(
    "/stats/course-count",
    summary="教师授课统计",
    response_model=ResponseModel[List[TeacherCourseStatResp]],
)
def teacher_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(
            Teacher.id.label("teacher_id"),
            Teacher.name.label("teacher_name"),
            func.count(teacher_course.c.course_id).label("course_count"),
            func.count(func.distinct(Student.id)).label("student_count"),
        )
        .select_from(Teacher)
        .join(teacher_course, Teacher.id == teacher_course.c.teacher_id, isouter=True)
        .join(Course, teacher_course.c.course_id == Course.id, isouter=True)
        .join(student_course, Course.id == student_course.c.course_id, isouter=True)
        .join(Student, student_course.c.student_id == Student.id, isouter=True)
        .group_by(Teacher.id, Teacher.name)
    )
    result = [row._asdict() for row in db.execute(stmt).all()]
    return ResponseModel.success(result)


@router.get(
    "/stats/dept",
    summary="按班级统计学生",
    response_model=ResponseModel[List[DeptStatResp]],
)
def dept_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(
            Dept.dept_name,
            func.count(Student.id).label("student_count"),
            func.coalesce(func.avg(Student.personal_score), 0).label(
                "avg_personal_score"
            ),
        )
        .select_from(Dept)
        .join(Student, Student.dept_id == Dept.id, isouter=True)
        .group_by(Dept.id, Dept.dept_name)
    )
    result = [row._asdict() for row in db.execute(stmt).all()]
    return ResponseModel.success(result)


@router.get(
    "/dept_student_count",
    summary="各班级学生人数统计",
    response_model=ResponseModel,
)
def get_dept_student_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(
            Dept.id.label("dept_id"),
            Dept.dept_name,
            func.count(Student.id).label("student_count"),
        )
        .select_from(Dept)
        .join(Student, Student.dept_id == Dept.id, isouter=True)
        .group_by(Dept.id, Dept.dept_name)
        .order_by(Dept.id.asc())
    )
    result = [row._asdict() for row in db.execute(stmt).all()]
    return ResponseModel.success(data=result)


@router.get(
    "/course_select_count",
    summary="各课程选课人数统计",
    response_model=ResponseModel,
)
def get_course_select_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(
            Course.id.label("course_id"),
            Course.course_name,
            func.count(student_course.c.student_id).label("student_count"),
        )
        .select_from(Course)
        .join(student_course, student_course.c.course_id == Course.id)
        .group_by(Course.id, Course.course_name)
        .order_by(Course.id.asc())
    )
    result = [row._asdict() for row in db.execute(stmt).all()]
    return ResponseModel.success(data=result)


@router.get(
    "/course_avg_score",
    summary="各课程平均分统计",
    response_model=ResponseModel,
)
def get_course_avg_score(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(
            Course.id.label("course_id"),
            Course.course_name,
            func.avg(student_course.c.score).label("avg_score"),
        )
        .select_from(Course)
        .join(student_course, student_course.c.course_id == Course.id)
        .group_by(Course.id, Course.course_name)
        .order_by(Course.id.asc())
    )
    result = []
    for row in db.execute(stmt).all():
        item = row._asdict()
        if item["avg_score"] is not None:
            item["avg_score"] = round(float(item["avg_score"]), 2)
        result.append(item)
    return ResponseModel.success(data=result)


@router.get(
    "/overview",
    summary="首页全局数据概览",
    response_model=ResponseModel,
)
def get_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    cache_key = "stats:overview"
    try:
        cache_data = redis_client.get(cache_key)
    except RedisError:
        cache_data = None
    if cache_data:
        return ResponseModel.success(data=json.loads(cache_data))

    result = {
        "total_student": db.scalar(select(func.count(Student.id))) or 0,
        "total_teacher": db.scalar(select(func.count(Teacher.id))) or 0,
        "total_course": db.scalar(select(func.count(Course.id))) or 0,
        "total_dept": db.scalar(select(func.count(Dept.id))) or 0,
    }
    try:
        redis_client.setex(
            cache_key,
            300,
            json.dumps(result, ensure_ascii=False),
        )
    except RedisError:
        pass
    return ResponseModel.success(data=result)
