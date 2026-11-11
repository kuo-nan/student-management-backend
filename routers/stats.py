"""管理员使用的统计查询接口，以及首页概览数据的Redis缓存（只有管理员才有权限）"""
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
            #教师可能教授多门课程，而一门课程可能有多个学生
            #连接后会出现重复学生记录，因此学生必须用DISTINCT
            func.count(func.distinct(Student.id)).label("student_count"),
        )
        .select_from(Teacher)
        #使用外连接暴露没有授课记录的教师
        .join(teacher_course, Teacher.id == teacher_course.c.teacher_id, isouter=True)
        .join(Course, teacher_course.c.course_id == Course.id, isouter=True)
        .join(student_course, Course.id == student_course.c.course_id, isouter=True)
        .join(Student, student_course.c.student_id == Student.id, isouter=True)
        #按教师分组，每位教师返回一条统计结果
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
            #空班级的平均值为NULL,使用coalesce转换为0
            #personal_score是学生个人评分，不是课程平均成绩
            func.coalesce(func.avg(Student.personal_score), 0).label(
                "avg_personal_score"
            ),
        )
        .select_from(Dept)
        #使用外连接暴露没有学生的班级
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
            #count(Student.id)只统计真实学生记录
            #空班级会被统计为0
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
            #student_id的数量就是选课人数
            func.count(student_course.c.student_id).label("student_count"),
        )
        .select_from(Course)
        #内连接表示只统计至少有一名选课学生的课程
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
            #使用student_course.score表示课程最终成绩，不要与ExamScore.exam_score
            #SQL AVG 会自动忽略NULL成绩
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
            #Decimal 转换为float并保留两位小数，便于JSON返回
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
        #先查Redis；命中时直接返回，避免执行四次COUNT查询
        cache_data = redis_client.get(cache_key)
    #Redis故障时把cache_data当作未命中
    #继续从MySQL读取，保证统计接口仍然可用
    except RedisError:
        cache_data = None
    if cache_data:
        #Redis客户端配置了 decode_responses=True,取出时已经是字符串
        #json.loads再转换成Python字典
        return ResponseModel.success(data=json.loads(cache_data))
    #缓存未命中时，使用四次COUNT生成首页概览
    #scalar()可能返回None,因此使用or 0保证响应是数字
    result = {
        "total_student": db.scalar(select(func.count(Student.id))) or 0,
        "total_teacher": db.scalar(select(func.count(Teacher.id))) or 0,
        "total_course": db.scalar(select(func.count(Course.id))) or 0,
        "total_dept": db.scalar(select(func.count(Dept.id))) or 0,
    }
    #当前使用固定TTL让缓存自然过期，没有在增删改查接口中主动删除缓存
    #因此数据更新后，首页统计最多可能有5分钟延迟
    try:
        #setex同时保存值和过期时间
        #300表示首页概览最多缓存5分钟
        redis_client.setex(
            cache_key,
            300,
            #ensure_ascii=False让中文以可读形式保存，而不是Unicode转义
            json.dumps(result, ensure_ascii=False),
        )
    #缓存写入失败不能让统计接口失败，因此这里直接忽略RedisError
    except RedisError:
        #Redis只是缓存，不是业务数据源
        #写缓存失败时仍然返回刚从MySQL查询到的结果
        pass
    return ResponseModel.success(data=result)
