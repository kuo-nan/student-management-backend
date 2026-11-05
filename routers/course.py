from io import BytesIO

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Course, User
from schemas import CourseCreate, CourseResp, PageResult, ResponseModel
from utils import add_operation_log, get_current_admin, paginate

router = APIRouter(prefix="/course", tags=["课程管理"])


@router.post(
    "/add_course",
    summary="新增课程",
    response_model=ResponseModel[CourseResp],
)
def create_course(
    course: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    db_course = Course(**course.model_dump())
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    add_operation_log(
        db,
        current_user,
        "课程管理",
        "新增",
        f"新增课程：{db_course.course_name}(ID:{db_course.id})",
    )
    return ResponseModel.success(data=db_course, message="新增成功")


@router.get(
    "/course_list",
    summary="查询课程列表",
    response_model=ResponseModel[PageResult[CourseResp]],
)
def get_course_list(
    name: str | None = Query(default=None, min_length=1, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    base_stmt = select(Course.id, Course.course_name, Course.credits)
    if name:
        base_stmt = base_stmt.where(Course.course_name.like(f"%{name}%"))
    result = paginate(db, base_stmt, page, page_size)
    return ResponseModel.success(data=result)


@router.post(
    "/import_excel",
    summary="Excel 批量导入课程",
    response_model=ResponseModel,
)
def import_course_excel(
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

    existing_names = set(db.scalars(select(Course.course_name)).all())
    course_list: list[Course] = []
    added_names: set[str] = set()
    fail_list: list[str] = []

    for row_idx, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        start=2,
    ):
        if all(cell is None for cell in row):
            continue
        try:
            course_name = str(row[0]).strip() if row[0] is not None else ""
            credits = int(row[1])
            if not course_name:
                raise ValueError("课程名称不能为空")
            if not 1 <= credits <= 10:
                raise ValueError("学分必须在 1-10 之间")
            if course_name in existing_names or course_name in added_names:
                raise ValueError("课程名称已存在")
            course_list.append(Course(course_name=course_name, credits=credits))
            added_names.add(course_name)
        except (IndexError, TypeError, ValueError) as exc:
            fail_list.append(f"第{row_idx}行：{exc}")

    db.add_all(course_list)
    db.commit()
    add_operation_log(
        db,
        current_user,
        "课程管理",
        "批量导入",
        f"导入课程：成功 {len(course_list)} 条，失败 {len(fail_list)} 条",
    )
    return ResponseModel.success(
        data={
            "success_count": len(course_list),
            "fail_count": len(fail_list),
            "fail_detail": fail_list,
        }
    )
