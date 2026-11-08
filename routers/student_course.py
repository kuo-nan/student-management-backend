from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Course, Dept, Student, User, student_course
from schemas import PageResult, ResponseModel, UpdateScoreRep
from utils import add_operation_log, get_current_admin, paginate

router = APIRouter(prefix="/select_course", tags=["选课管理"])


class SelectCourseReq(BaseModel):
    student_id: int = Field(ge=1)
    course_id: int = Field(ge=1)


@router.post("/select", summary="给学生选课", response_model=ResponseModel)
def select_course(
    req: SelectCourseReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    student = db.get(Student, req.student_id)
    course = db.get(Course, req.course_id)
    if not student or not course:
        raise HTTPException(status_code=404, detail="学生或课程不存在")
    exists = db.scalar(
        select(student_course.c.student_id).where(
            student_course.c.student_id == req.student_id,
            student_course.c.course_id == req.course_id,
        )
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="学生已经选择此课程")
    try:
        db.execute(
            insert(student_course).values(
                student_id=req.student_id,
                course_id=req.course_id,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="学生已经选择此课程") from None
    add_operation_log(
        db,
        current_user,
        "选课管理",
        "选课",
        f"学生 {student.name} 选择课程 {course.course_name}",
    )
    return ResponseModel.success(message="选课成功")


@router.delete(
    "/drop/{student_id}/{course_id}",
    summary="学生退课",
    response_model=ResponseModel,
)
def drop_course(
    student_id: int = Path(ge=1),
    course_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    student = db.get(Student, student_id)
    course = db.get(Course, course_id)
    if not student or not course:
        raise HTTPException(status_code=404, detail="学生或课程不存在")
    result = db.execute(
        delete(student_course).where(
            student_course.c.student_id == student_id,
            student_course.c.course_id == course_id,
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="学生未选择此课程")
    db.commit()
    add_operation_log(
        db,
        current_user,
        "选课管理",
        "退课",
        f"学生 {student.name} 退选课程 {course.course_name}",
    )
    return ResponseModel.success(message="退课成功")


@router.get(
    "/student_course/{student_id}",
    summary="查询学生已选课程",
    response_model=ResponseModel[PageResult[dict]],
)
def get_student_course(
    student_id: int = Path(ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if not db.get(Student, student_id):
        raise HTTPException(status_code=404, detail="学生不存在")
    base_stmt = (
        select(Course.id, Course.course_name, Course.credits)
        .select_from(student_course)
        .join(Course, student_course.c.course_id == Course.id)
        .where(student_course.c.student_id == student_id)
        .order_by(Course.id.desc())
    )
    return ResponseModel.success(data=paginate(db, base_stmt, page, page_size))


@router.get(
    "/course_students/{course_id}",
    summary="查询课程学生",
    response_model=ResponseModel[PageResult[dict]],
)
def get_course_students(
    course_id: int = Path(ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if not db.get(Course, course_id):
        raise HTTPException(status_code=404, detail="课程不存在")
    base_stmt = (
        select(
            Student.id,
            Student.name,
            Student.age,
            Student.personal_score,
            Student.dept_id,
            Dept.dept_name,
            student_course.c.score.label("course_score"),
        )
        .select_from(student_course)
        .join(Student, student_course.c.student_id == Student.id)
        .join(Dept, Student.dept_id == Dept.id, isouter=True)
        .where(student_course.c.course_id == course_id)
        .order_by(Student.id.desc())
    )
    return ResponseModel.success(data=paginate(db, base_stmt, page, page_size))


@router.post(
    "/update_score",
    summary="录入或修改课程成绩",
    response_model=ResponseModel,
)
def update_course_score(
    req: UpdateScoreRep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    student = db.get(Student, req.student_id)
    course = db.get(Course, req.course_id)
    if not student or not course:
        raise HTTPException(status_code=404, detail="学生或课程不存在")
    result = db.execute(
        update(student_course)
        .where(
            student_course.c.student_id == req.student_id,
            student_course.c.course_id == req.course_id,
        )
        .values(score=req.score)
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="学生未选择此课程，无法录入成绩")
    db.commit()
    add_operation_log(
        db,
        current_user,
        "成绩管理",
        "录入成绩",
        f"学生 {student.name} 课程 {course.course_name} 成绩 {req.score}",
    )
    return ResponseModel.success(message="成绩更新成功")


@router.get(
    "/student_report/{student_id}",
    summary="查询学生成绩单",
    response_model=ResponseModel,
)
def get_student_report(
    student_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    courses = db.execute(
        select(
            Course.id,
            Course.course_name,
            student_course.c.score,
        )
        .select_from(student_course)
        .join(Course, student_course.c.course_id == Course.id)
        .where(student_course.c.student_id == student_id)
        .order_by(Course.id.desc())
    ).all()
    course_list = [row._asdict() for row in courses]
    scores = [row["score"] for row in course_list if row["score"] is not None]
    result = {
        "student_id": student.id,
        "student_name": student.name,
        "total_course": len(course_list),
        "scored_course": len(scores),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "course_list": course_list,
    }
    return ResponseModel.success(data=result)


@router.get(
    "/course_rank/{course_id}",
    summary="查询课程成绩排名",
    response_model=ResponseModel,
)
def get_course_rank(
    course_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    rows = db.execute(
        select(
            Student.id,
            Student.name,
            student_course.c.score,
        )
        .select_from(student_course)
        .join(Student, student_course.c.student_id == Student.id)
        .where(student_course.c.course_id == course_id)
        .order_by(student_course.c.score.desc(), Student.id.asc())
    ).all()
    rank_list = [
        {"rank": index, **row._asdict()}
        for index, row in enumerate(rows, start=1)
    ]
    return ResponseModel.success(
        data={
            "course_id": course.id,
            "course_name": course.course_name,
            "total_student": len(rank_list),
            "rank_list": rank_list,
        }
    )
