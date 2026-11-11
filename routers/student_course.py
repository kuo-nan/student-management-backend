"""学生选课、课程成绩和成绩报表管理接口."""
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

#选课请求只包含学生ID和课程ID,并且Pydantic保证大于等于1
class SelectCourseReq(BaseModel):
    student_id: int = Field(ge=1)
    course_id: int = Field(ge=1)


@router.post("/select", summary="给学生选课", response_model=ResponseModel)
def select_course(
    req: SelectCourseReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    #检查学生和课程是否真实存在，避免写入无效外键
    student = db.get(Student, req.student_id)
    course = db.get(Course, req.course_id)
    if not student or not course:
        raise HTTPException(status_code=404, detail="学生或课程不存在")
    #预查询用于尽早返回409
    #真正防止并发重复选课的是中间表联合主键
    exists = db.scalar(
        select(student_course.c.student_id).where(
            student_course.c.student_id == req.student_id,
            student_course.c.course_id == req.course_id,
        )
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="学生已经选择此课程")
    try:
        #直接向student_course插入关联记录，不修改Student和Course表
        db.execute(
            insert(student_course).values(
                student_id=req.student_id,
                course_id=req.course_id,
            )
        )
        db.commit()
    #并发请求可能同时通过预查询
    #最终只有一个INSERT成功，另外一个触发IntegrityError
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
            #把学生ID和课程ID同时作为删除条件
            #删除范围精确限制在一条选课关系
            student_course.c.student_id == student_id,
            student_course.c.course_id == course_id,
        )
    )
    #rowcount为0表示这条选课关系不存在
    if result.rowcount == 0:
        #没有匹配记录时回滚当前事务并返回400
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
        #从student_course出发,连接Course查询学生已选课程
        .join(Course, student_course.c.course_id == Course.id)
        .where(student_course.c.student_id == student_id)
        .order_by(Course.id.desc())
    )
    #该接口返回课程基本信息，不包含course_score
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
            #student_course.score是用别名course_score，避免和personal_score混淆
            student_course.c.score.label("course_score"),
        )
        .select_from(student_course)
        #从选课中间表连接Student,查询课程中的学生和课程最终成绩
        .join(Student, student_course.c.student_id == Student.id)
        #左连接Dept,是为了返回班级名称
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
    #UpdateScoreRep已经通过Pydantic校验成绩在0到100之间
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
        #更新目标是一条选课关系
        .values(score=req.score)
    )
    #rowcount为0表示学生没有选择这门课
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
    #该接口修改的是课程最终成绩,不是某次ExamScore
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
    #先查询学生全部课程及其课程最终成绩
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
        "total_course": len(course_list), #统计全部已选课程
        "scored_course": len(scores),  #只统计已经录入非空成绩的课程
        #计算平均分是忽略NULL成绩，避免未录入的课程被当作0分
        #没有任何成绩时返回None,而不是让除0错误发生
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
        #按课程成绩降序排列，成绩相同时按学生ID升序，保证输出顺序稳定
        .order_by(student_course.c.score.desc(), Student.id.asc())
    ).all()
    rank_list = [
        {"rank": index, **row._asdict()}
        #enumerate产生的时普通顺序排名，不是SQL RANK（）
        #同分学生仍然会得到不同名次
        #当前查询没有排除score为NULL的选课记录
        # 未录入成绩的学生也会进入排名列表
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
