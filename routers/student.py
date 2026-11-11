"""学生查询、新增和修改的HTTP接口层"""
from io import BytesIO

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import Course, Dept, Student, User, student_course
from schemas import (
    PageResult,
    ResponseModel,
    StudentBase,
    StudentCourseStatResp,
    StudentCreate,
    StudentResp,
    StudentUpdate,
)
from services.student_service import (
    create_student,
    get_student_page,
    update_student_service,
)
from utils import add_operation_log, get_current_admin

router = APIRouter(prefix="/student", tags=["学生管理"])


@router.get(
    "/list",
    summary="学生列表",
    response_model=ResponseModel[PageResult[StudentResp]],
)
def get_students(
    student_no: int | None = Query(default=None, ge=1),
    name: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    #学生列表只允许管理员访问，认证和角色校验由Depends完成
    current_user: User = Depends(get_current_admin),
):
    #路由层只负责接受参数，实际查询逻辑放在student_srvice中
    return ResponseModel.success(data=get_student_page
    (db, page, page_size, student_no=student_no,name=name))


@router.post(
    "/add_student",
    summary="新增学生",
    response_model=ResponseModel[StudentBase],
)
def add_student(
    student: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    #预先查询用于快速返回409
    exists = db.scalar(select(Student.id).where(Student.student_no == student.student_no))
    if exists is not None:
        #学号重复返回409
        raise HTTPException(status_code=409, detail="学号已存在")
    if not db.get(Dept, student.dept_id):
        #班级不存在在返回404
        raise HTTPException(status_code=404, detail="班级不存在")
    try:
        #真正防止并发重复学号的是 create_student中的数据库唯一约束
        created = create_student(db, student)
    except ValueError as exc:
        #将学号重复转换成ValueError，路由层再转换成HTTP409
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return ResponseModel.success(data=created, message="新增成功")


@router.delete(
    "/delete_student/{stu_id}",
    summary="删除学生",
    response_model=ResponseModel,
)
def delete_student(
    stu_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    db_student = db.get(Student, stu_id)
    if not db_student:
        raise HTTPException(status_code=404, detail="学生不存在")

    name = db_student.name
    db.delete(db_student)
    try:
        db.commit()
    except IntegrityError:
        #数据库约束报错是必须rollback，否则当前Session会停留在失败事务
        db.rollback()
        #学生如果仍有选课，成绩或请假记录，外键约束会阻止删除
        raise HTTPException(
            #这里返回409，因为请求本身格式正确，但现有数据产生了冲突
            status_code=409,
            detail="该学生仍有关联的选课、成绩或请假记录，不能直接删除",
        ) from None
    add_operation_log(
        db,
        current_user,
        "学生管理",
        "删除",
        f"删除学生：{name}(ID:{stu_id})",
    )
    return ResponseModel.success(message="删除成功")


@router.put(
    "/update_student/{stu_id}",
    summary="修改学生信息",
    response_model=ResponseModel[StudentBase],
)
def update_student(
    #StudentUpdate 没有student_no,因此学号不允许在此接口修改
    #StudentUpdate的所有字段都是可选的
    student: StudentUpdate,
    stu_id: int = Path(ge=1),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    #只有客户端提供了dept_id时才会检查班级，避免未修改班级的请求被误拦截
    if student.dept_id is not None and not db.get(Dept, student.dept_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    try:
        #service内使用exclude_unset实现部分字段更新
        updated = update_student_service(db, stu_id, student)
        return ResponseModel.success(data=updated)
    except ValueError as exc:
        #学生不存在由service通过ValueError报出，路由层转换为HTTP404
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post(
    "/course_by_student/{stu_id}/{course_id}",
    summary="给学生选课",
    response_model=ResponseModel,
)
def select_course(
    stu_id: int = Path(ge=1),
    course_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    student = db.get(Student, stu_id)
    course = db.get(Course, course_id)
    if not student or not course:
        raise HTTPException(status_code=404, detail="学生或课程不存在")
    #student.courses通过student_course中间表查询已选课程
    #先检查是否已选，用于返回更友好的409
    if course in student.courses:
        raise HTTPException(status_code=409, detail="学生已选过此课程")
    #append 不会修改Course 表
    # commit时 SQLAlchemy 会向student_course插入一条关联记录
    student.courses.append(course)
    try:
        db.commit()
    #并发选课时，两个请求可能同时通过python检查
    #最终依靠中间表的联合主键(student_id,course_id)防止重复
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="学生已选过此课程") from None
    add_operation_log(
        db,
        current_user,
        "选课管理",
        "选课",
        f"学生 {student.name} 选择课程 {course.course_name}",
    )
    return ResponseModel.success(message="选课成功")


@router.delete(
    "/student_leave_course/{stu_id}/{course_id}",
    summary="取消选课",
    response_model=ResponseModel,
)
def drop_course(
    stu_id: int = Path(ge=1),
    course_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    student = db.get(Student, stu_id)
    course = db.get(Course, course_id)
    if not student or not course:
        raise HTTPException(status_code=404, detail="学生或课程不存在")
    #当前课程不在关联列表中返回400,因为请求指向了一个无效的退课操作
    if course not in student.courses:
        raise HTTPException(status_code=400, detail="学生未选过此课程")
    #remove删除的时student_course中的关联记录，不会删除Course或Student
    student.courses.remove(course)
    db.commit()
    add_operation_log(
        db,
        current_user,
        "选课管理",
        "退课",
        f"学生 {student.name} 退选课程 {course.course_name}",
    )
    return ResponseModel.success(message="取消选课成功")


@router.get(
    "/student_with_courses/{stu_id}",
    summary="查询学生的所有选课",
    response_model=ResponseModel[StudentCourseStatResp],
)
def get_student_courses(
    stu_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = (
        select(Student)
        #提前加载课程和班级关系，避免后续访问student.coursess 时产生额外查询
        .options(selectinload(Student.courses), selectinload(Student.dept))
        .where(Student.id == stu_id)
    )
    student = db.scalar(stmt)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ResponseModel.success(
        #响应中明确组织学生基本信息和课程列表，避免把完整ORM对象直接暴露出去
        data={
            "student_no": student.student_no,
            "id": student.id,
            "name": student.name,
            "age": student.age,
            "personal_score": student.personal_score,
            "dept_id": student.dept_id,
            "dept_name": student.dept.dept_name if student.dept else None,
            "courses": student.courses,
        }
    )


@router.post(
    "/batch_select_course/{dept_id}/{course_id}",
    summary="给班级批量选课",
    response_model=ResponseModel[dict],
)
def batch_select_course(
    dept_id: int = Path(ge=1),
    course_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if not db.get(Dept, dept_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    if not db.get(Course, course_id):
        raise HTTPException(status_code=404, detail="课程不存在")
    #INSERT ...SELECT会找出该班级的全部学生
    stmt = mysql_insert(student_course).from_select(
        ["student_id", "course_id"],
        select(Student.id, course_id).where(Student.dept_id == dept_id),
    )
    #用一条SQL批量写入他们的选课关系
    stmt = stmt.on_duplicate_key_update(
        student_id=stmt.inserted.student_id,
        course_id=stmt.inserted.course_id,
    )
    #已经存在相同（student_id,course_id）时不报错，也不重复插入
    try:
        result = db.execute(stmt)
        db.commit()
    except IntegrityError:
        #批量写库失败时回滚，避免只给部分学生选上课
        db.rollback()
        raise HTTPException(status_code=409, detail="批量选课发生数据冲突") from None
    return ResponseModel.success(
        #MySQL可能把实际插入和重复更新都计入，因此不能直接当做“新增学生人数"
        data={"affected_rows": result.rowcount},  # rowcount是数据库报告的受影响行数
        message="批量选课成功",
    )


@router.post(
    "/import_excel",
    summary="Excel 批量导入学生",
    response_model=ResponseModel,
)
def import_student_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    filename = file.filename or ""
    #只接受.xlsx，避免旧版.xls或伪造扩展名交给openpyxl
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    try:
        #data_only=True 读取公式单元格的缓存计算结果，而不是公式文本
        workbook = openpyxl.load_workbook(BytesIO(file.file.read()), data_only=True)
        sheet = workbook.active
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 文件格式错误：{exc}") from None

    success_count = 0
    fail_list: list[str] = []
    student_list: list[Student] = []
    #一次性读取数据库已有学号，避免没处理一行都查询数据库
    existing_student_nos = set(db.scalars(select(Student.student_no)).all())
    #记录已导入的学号，避免重复
    imported_student_nos: set[int] = set()
    dept_ids = {
        value
        #一次性读取所有有效班级ID,逐行校验时直接使用内存集合
        for value in db.scalars(select(Dept.id)).all()
    }

    for row_idx, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        start=2,  #从第二行开始，默认第一行是表头
    ):
        if all(cell is None for cell in row):
            continue
        try:
            student_no, name, age, personal_score, dept_id = row[:5]
            student_no = int(student_no)
            name = str(name).strip() if name is not None else ""
            #单行校验失败只记录行号和原因，不中断其他行
            if not student_no:
                raise ValueError("学号不能为空")
            if student_no<=0:
                raise ValueError("学号必须大于0")
            if (
                student_no in existing_student_nos
                or student_no in imported_student_nos
            ):
                raise ValueError("学号已存在或文件内重复")
            if not name:
                raise ValueError("姓名不能为空")
            age = int(age)
            personal_score = int(personal_score)
            dept_id = int(dept_id)
            if not 1 <= age <= 150:
                raise ValueError("年龄必须在 1-150 之间")
            if not 0 <= personal_score <= 100:
                raise ValueError("个人评分必须在 0-100 之间")
            if dept_id not in dept_ids:
                raise ValueError("班级ID不存在")
            student_list.append(
                Student(
                    student_no=student_no,
                    name=name,
                    age=age,
                    personal_score=personal_score,
                    dept_id=dept_id,
                )
            )
            imported_student_nos.add(student_no)
        except (TypeError, ValueError) as exc:
            fail_list.append(f"第{row_idx}行：{exc}")
    #同时检查数据库已有学号和文件内部重复学号
    #只有全部字段校验通过的学生才能加入待提交列表和imported_student_nos
    try:
        #所有合法学生统一add_all后一次commit
        db.add_all(student_list)
        db.commit()
        success_count = len(student_list)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="导入期间发生学号冲突，请重新导入",
        ) from None
    # 校验失败的行只是被跳过，不属于数据库事务，但一旦commit遇到学号冲突，合法批次也会整体回滚
    except Exception:
        db.rollback()
        raise
   

    add_operation_log(
        db,
        current_user,
        "学生管理",
        "批量导入",
        f"导入学生：成功 {success_count} 条，失败 {len(fail_list)} 条",
    )
    #操作日志和导入业务分开提交，因此日志写入失败不会撤销已经导入的学生
    return ResponseModel.success(
        data={
            #只有commit成功后才设置成功数量
            "success_count": success_count,
            "fail_count": len(fail_list),
            "fail_detail": fail_list,
        }
    )
