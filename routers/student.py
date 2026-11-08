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
    current_user: User = Depends(get_current_admin),
):
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
    exists = db.scalar(select(Student.id).where(Student.student_no == student.student_no))
    if exists is not None:
        raise HTTPException(status_code=409, detail="学号已存在")
    if not db.get(Dept, student.dept_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    try:
        created = create_student(db, student)
    except ValueError as exc:
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
        db.rollback()
        raise HTTPException(
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
    student: StudentUpdate,
    stu_id: int = Path(ge=1),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if student.dept_id is not None and not db.get(Dept, student.dept_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    try:
        updated = update_student_service(db, stu_id, student)
        return ResponseModel.success(data=updated)
    except ValueError as exc:
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
    if course in student.courses:
        raise HTTPException(status_code=409, detail="学生已选过此课程")
    student.courses.append(course)
    try:
        db.commit()
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
    if course not in student.courses:
        raise HTTPException(status_code=400, detail="学生未选过此课程")
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
        .options(selectinload(Student.courses), selectinload(Student.dept))
        .where(Student.id == stu_id)
    )
    student = db.scalar(stmt)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ResponseModel.success(
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

    stmt = mysql_insert(student_course).from_select(
        ["student_id", "course_id"],
        select(Student.id, course_id).where(Student.dept_id == dept_id),
    )
    stmt = stmt.on_duplicate_key_update(
        student_id=stmt.inserted.student_id,
        course_id=stmt.inserted.course_id,
    )
    try:
        result = db.execute(stmt)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="批量选课发生数据冲突") from None
    return ResponseModel.success(
        data={"affected_rows": result.rowcount},
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
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    try:
        workbook = openpyxl.load_workbook(BytesIO(file.file.read()), data_only=True)
        sheet = workbook.active
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 文件格式错误：{exc}") from None

    success_count = 0
    fail_list: list[str] = []
    student_list: list[Student] = []
    existing_student_nos = set(db.scalars(select(Student.student_no)).all())
    imported_student_nos: set[int] = set()
    dept_ids = {
        value
        for value in db.scalars(select(Dept.id)).all()
    }

    for row_idx, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        start=2,
    ):
        if all(cell is None for cell in row):
            continue
        try:
            student_no, name, age, personal_score, dept_id = row[:5]
            student_no = int(student_no)
            name = str(name).strip() if name is not None else ""
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

    try:
        db.add_all(student_list)
        db.commit()
        success_count = len(student_list)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="导入期间发生学号冲突，请重新导入",
        ) from None
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
    return ResponseModel.success(
        data={
            "success_count": success_count,
            "fail_count": len(fail_list),
            "fail_detail": fail_list,
        }
    )
