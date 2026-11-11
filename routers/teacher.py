"""教师基本信息、教师课程和教师班级关联的管理接口"""
from io import BytesIO

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import (
    Course,
    Dept,
    Student,
    Teacher,
    User,
    student_course,
    teacher_course,
    teacher_dept,
)
from schemas import (
    PageResult,
    ResponseModel,
    StudentResp,
    TeacherCreate,
    TeacherResp,
    TeacherWithCoursesResp,
)
from utils import add_operation_log, get_current_admin, paginate

router = APIRouter(prefix="/teacher", tags=["教师管理"])


@router.post(
    "/add_teacher",
    summary="新增教师",
    response_model=ResponseModel[TeacherResp],
)
def add_teacher(
    #TeacherCreate已通过Pydantic校验姓名和职称不能为空
    teacher: TeacherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    db_teacher = Teacher(**teacher.model_dump())
    #add只创建Teacher，commit后才写入数据库和生成自增ID
    #当前没有教师姓名唯一约束，因此允许同名教师
    db.add(db_teacher)
    db.commit()
    db.refresh(db_teacher)
    add_operation_log(
        db,
        current_user,
        "教师管理",
        "新增",
        f"新增教师：{db_teacher.name}(ID:{db_teacher.id})",
    )
    return ResponseModel.success(data=db_teacher, message="新增成功")


@router.post(
    "/teacher_with_course/{teacher_id}/{course_id}",
    summary="给教师分配课程",
    response_model=ResponseModel,
)
def add_course_to_teacher(
    course_id: int = Path(ge=1),
    teacher_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    teacher = db.get(Teacher, teacher_id)
    course = db.get(Course, course_id)
    if not teacher or not course:
        raise HTTPException(status_code=404, detail="教师或课程不存在")
    if course in teacher.courses:
        # teacher.courses通过teacher_course中间表读取教师负责的课程
        #先检查是否已关联，方便返回409
        raise HTTPException(status_code=409, detail="教师已负责该课程")
    #append后提交事务，SQLALchemy会向teacher_course插入一条记录
    #联合主键(teacher_id,course_id)会阻止重复关联
    try:
        teacher.courses.append(course)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="教师已负责该课程") from None
    add_operation_log(
        db,
        current_user,
        "教师课程管理",
        "分配课程",
        f"教师 {teacher.name} 负责课程 {course.course_name}",
    )
    return ResponseModel.success(message="分配成功")


@router.get(
    "/teacher_courses",
    summary="查看教师的课程",
    response_model=ResponseModel[list[TeacherWithCoursesResp]],
)
def get_teacher_courses(
    name: str | None = Query(default=None, max_length=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    #joinedload提前加载教师课程，避免序列化响应时产生N+1查询
    stmt = select(Teacher).options(joinedload(Teacher.courses))
    if name:
        stmt = stmt.where(Teacher.name.like(f"%{name}%"))
    #joinedload集合关系可能产生重复Teacher行
    #unique()让SQLAlchemy去实体去重
    teachers = db.scalars(stmt).unique().all()
    return ResponseModel.success(data=teachers)


@router.post(
    "/teacher_with_dept/{teacher_id}/{dept_id}",
    summary="给教师绑定班级",
    response_model=ResponseModel,
)
def add_dept_to_teacher(
    teacher_id: int = Path(ge=1),
    dept_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    teacher = db.get(Teacher, teacher_id)
    dept = db.get(Dept, dept_id)
    if not teacher or not dept:
        raise HTTPException(status_code=404, detail="教师或班级不存在")
    if dept in teacher.depts:
        raise HTTPException(status_code=409, detail="教师已绑定该班级")
    #teacher.depts通过teacher_dept中间表保存教师负责的班级
    #联合主键（teacher_id,dept_id）防止同一关系重复写入
    try:
        teacher.depts.append(dept)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="教师已绑定该班级") from None
    return ResponseModel.success(message="绑定成功")


@router.delete(
    "/teacher_leave_dept/{teacher_id}/{dept_id}",
    summary="取消教师班级绑定",
    response_model=ResponseModel,
)
def drop_dept_from_teacher(
    teacher_id: int = Path(ge=1),
    dept_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    teacher = db.get(Teacher, teacher_id)
    dept = db.get(Dept, dept_id)
    if not teacher or not dept:
        raise HTTPException(status_code=404, detail="教师或班级不存在")
    if dept not in teacher.depts:
        raise HTTPException(status_code=400, detail="教师未绑定该班级")
    #remove删除的是teacher_dept关联记录
    #不会删除Teacher或Dept本身
    teacher.depts.remove(dept)
    db.commit()
    return ResponseModel.success(message="取消绑定成功")


@router.get(
    "/teacher_list",
    summary="分页查询教师",
    response_model=ResponseModel[PageResult[TeacherResp]],
)
def get_teacher_list(
    name: str | None = Query(default=None, max_length=20),
    title: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    #只选择分页响应需要的字段
    #name做包含匹配,title做精准匹配
    base_stmt = select(Teacher.id, Teacher.name, Teacher.title)
    if name:
        base_stmt = base_stmt.where(Teacher.name.like(f"%{name}%"))
    if title:
        base_stmt = base_stmt.where(Teacher.title == title)
    return ResponseModel.success(data=paginate(db, base_stmt, page, page_size))


@router.get(
    "/teachers_by_course/{course_id}",
    summary="查询课程教师",
    response_model=ResponseModel[list[TeacherResp]],
)
def get_teachers_by_course(
    course_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(Teacher)
        .distinct()
        #通过teacher_course查询所有负责该课程的教师
        .join(teacher_course, Teacher.id == teacher_course.c.teacher_id)
        .where(teacher_course.c.course_id == course_id)
    )
    return ResponseModel.success(data=db.scalars(stmt).all())


@router.get(
    "/students_by_teacher/{teacher_id}",
    summary="查询教师课程中的学生",
    response_model=ResponseModel[list[StudentResp]],
)
def get_students_by_teacher(
    teacher_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(
            Student.student_no,
            Student.id,
            Student.name,
            Student.age,
            Student.personal_score,
            Student.dept_id,
            Dept.dept_name,
        )
        .distinct()
        .join(student_course, Student.id == student_course.c.student_id)
        .join(Course, student_course.c.course_id == Course.id)
        .join(teacher_course, Course.id == teacher_course.c.course_id)
        .join(Dept,Student.dept_id==Dept.id)
        .where(teacher_course.c.teacher_id == teacher_id)
    )
    result = [row._asdict() for row in db.execute(stmt).all()]
    return ResponseModel.success(data=result)


@router.get(
    "/students_by_teacher_dept/{dept_id}/{teacher_id}",
    summary="查询教师所带班级中的选课学生",
    response_model=ResponseModel[list[StudentResp]],
)
def get_students_by_teacher_dept(
    dept_id: int = Path(ge=1),
    teacher_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(
            Student.student_no,
            Student.id,
            Student.name,
            Student.age,
            Student.personal_score,
            Student.dept_id,
            Dept.dept_name,
        )
        .distinct()
        .join(student_course, Student.id == student_course.c.student_id)
        .join(Course, student_course.c.course_id == Course.id)
        .join(teacher_course, Course.id == teacher_course.c.course_id)
        .join(Dept, Student.dept_id == Dept.id)
        .where(
            teacher_course.c.teacher_id == teacher_id,
            #在”教师课程中的学生“基础上，再用Student.dept_id限定班级
            #Dept只用于返回班级名称，学会筛选条件人使用Student.dept_id
            Student.dept_id == dept_id,
        )
    )
    result = [row._asdict() for row in db.execute(stmt).all()]
    return ResponseModel.success(data=result)


@router.get(
    "/stats/filter",
    summary="按授课数和学生数筛选教师",
    response_model=ResponseModel[list[TeacherResp]],
)
def filter_teacher_by_stats(
    name: str | None = Query(default=None, max_length=20),
    min_course: int | None = Query(default=None, ge=0),
    max_student: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(Teacher)
        #外连接保留没有课程或没有学生的教师
        .join(teacher_course, Teacher.id == teacher_course.c.teacher_id, isouter=True)
        .join(Course, teacher_course.c.course_id == Course.id, isouter=True)
        .join(student_course, Course.id == student_course.c.course_id, isouter=True)
    )
    if name:
        stmt = stmt.where(Teacher.name.like(f"%{name}%"))
    stmt = stmt.group_by(Teacher.id, Teacher.name, Teacher.title)
    #按教师分组后,HAVING用于筛选聚合统计的结果
    #DISTINCT防止教师教授多门课，课程包含多个学生时重复计数
    if min_course is not None:
        stmt = stmt.having(
            func.count(func.distinct(teacher_course.c.course_id)) >= min_course
        )
    if max_student is not None:
        stmt = stmt.having(
            func.count(func.distinct(student_course.c.student_id)) <= max_student
        )
    return ResponseModel.success(data=db.scalars(stmt).all())


@router.delete(
    "/delete_teacher/{teacher_id}",
    summary="删除教师及关联关系",
    response_model=ResponseModel,
)
def delete_teacher(
    teacher_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    teacher_name = teacher.name
    #当前模型没有配置自动级联删除
    #因此先手动删除两个中间表中的关联记录
    db.execute(delete(teacher_course).where(teacher_course.c.teacher_id == teacher_id))
    db.execute(delete(teacher_dept).where(teacher_dept.c.teacher_id == teacher_id))
    db.delete(teacher)
    #删除teacher_course、teacher_dept和Teacher共用一个数据
    #最后统一commit,避免留下半删除状态
    db.commit()
    add_operation_log(
        db,
        current_user,
        "教师管理",
        "删除",
        f"删除教师：{teacher_name}(ID:{teacher_id})",
    )
    return ResponseModel.success(message="删除成功")


@router.get(
    "/teacher/{course_id}",
    summary="通过课程查询教师",
    response_model=ResponseModel[list[TeacherResp]],
)
def get_course_teachers(
    course_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return ResponseModel.success(data=course.teachers)


@router.put(
    "/batch/transfer-course/{from_teacher_id}/{new_teacher_id}",
    summary="批量转授课程",
    response_model=ResponseModel,
)
def batch_transfer_course(
    from_teacher_id: int = Path(ge=1),
    new_teacher_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if from_teacher_id == new_teacher_id:
        raise HTTPException(status_code=400, detail="原教师和目标教师不能相同")
    if not db.get(Teacher, from_teacher_id):
        raise HTTPException(status_code=404, detail="原教师不存在")
    if not db.get(Teacher, new_teacher_id):
        raise HTTPException(status_code=404, detail="目标教师不存在")

    source_courses = set(
        db.scalars(
            select(teacher_course.c.course_id).where(
                teacher_course.c.teacher_id == from_teacher_id
            )
        ).all()
    )
    target_courses = set(
        db.scalars(
            select(teacher_course.c.course_id).where(
                teacher_course.c.teacher_id == new_teacher_id
            )
        ).all()
    )
    #source_courses&targe_courses得到两位教师共同负责的课程
    duplicate_courses = source_courses & target_courses
    #目标教师已经负责的课程不能直接UPDATE
    #否则(teacher_id,course_id)会违反联合主键
    #先删除重复关联，再把员教师剩余的课程全部转给目标教师
    if duplicate_courses:
        db.execute(
            delete(teacher_course).where(
                teacher_course.c.teacher_id == from_teacher_id,
                teacher_course.c.course_id.in_(duplicate_courses),
            )
        )
    db.execute(
        update(teacher_course)
        .where(teacher_course.c.teacher_id == from_teacher_id)
        .values(teacher_id=new_teacher_id)
    )
    #再次写操作再统一事务中提交，避免只转授一部分课程
    db.commit()
    add_operation_log(
        db,
        current_user,
        "教师管理",
        "转授课程",
        f"将教师 {from_teacher_id} 的课程转给教师 {new_teacher_id}",
    )
    return ResponseModel.success(message="转授成功")


@router.post(
    "/import_excel",
    summary="Excel 批量导入教师",
    response_model=ResponseModel,
)
def import_teacher_excel(
    #教师Excel不经过TeacherCreate，因此需要手动检查姓名和职称
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")
    try:
        workbook = openpyxl.load_workbook(BytesIO(file.file.read()), data_only=True)
        sheet = workbook.active
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 文件格式错误：{exc}") from None

    teacher_list: list[Teacher] = []
    fail_list: list[str] = []
    for row_idx, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        start=2,
    ):
        # 空白行跳过，单行错误记录后后继续处理合法行
        if all(cell is None for cell in row):
            continue
        try:
            name = str(row[0]).strip() if row[0] is not None else ""
            title = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
            if not name:
                raise ValueError("姓名不能为空")
            if not title:
                raise ValueError("职称不能为空")
            teacher_list.append(Teacher(name=name, title=title))
        except (IndexError, TypeError, ValueError) as exc:
            fail_list.append(f"第{row_idx}行：{exc}")
    #合法教师统一add_all，最后一次commit
    db.add_all(teacher_list)
    db.commit()
    # Excel目前只检查非空，没有检查Teacher字段的最大长度
    # JSON接口则由TeacherCreate自动检查
    add_operation_log(
        db,
        current_user,
        "教师管理",
        "批量导入",
        f"导入教师：成功 {len(teacher_list)} 条，失败 {len(fail_list)} 条",
    )
    return ResponseModel.success(
        data={
            "success_count": len(teacher_list),
            "fail_count": len(fail_list),
            "fail_detail": fail_list,
        }
    )
    
