"""课程新增、查询和Excel批量导入接口"""
from io import BytesIO

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
    #CourseCreate已经通过Pydantic校验学分在1到10之间
    course: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    # 预查询用于尽早提示重名，数据库唯一约束负责处理并发兜底。
    if db.scalar(select(Course.id).where(Course.course_name == course.course_name)):
        raise HTTPException(status_code=409, detail="课程名称已存在")

    db_course = Course(**course.model_dump())
    db.add(db_course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="课程名称已存在") from None
    #commit后refresh，返回数据库生成的自增ID
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
    #查询只选择id,course_name,credits三个响应字段
    base_stmt = select(Course.id, Course.course_name, Course.credits)
    if name:
        #name使用包含匹配，只有传入关键字时才追加筛选条件
        base_stmt = base_stmt.where(Course.course_name.like(f"%{name}%"))
    result = paginate(db, base_stmt, page, page_size)
    return ResponseModel.success(data=result)


@router.post(
    "/import_excel",
    summary="Excel 批量导入课程",
    response_model=ResponseModel,
)
def import_course_excel(
    #Excel导入绕过Pydantic，因此格式、空值和学分返回都要在这里手动校验
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")
    try:
        #data_only=True 读取公式单元格的缓存结果
        workbook = openpyxl.load_workbook(BytesIO(file.file.read()), data_only=True)
        sheet = workbook.active
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 文件格式错误：{exc}") from None
    # 一次性读取数据库中已有的课程名称
    existing_names = set(db.scalars(select(Course.course_name)).all())
    course_list: list[Course] = []
    #added_names记录当前文件中已经出现的名称
    #防止同一文件内重复导入
    added_names: set[str] = set()
    fail_list: list[str] = []
    
    for row_idx, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        #从第二行开始。默认第一行是表头
        start=2,
    ):
        #空白行直接跳过，不计入成功和失败
        if all(cell is None for cell in row):
            continue
        try:
            #row[0]是课程名称，row[1]是学分
            course_name = str(row[0]).strip() if row[0] is not None else ""
            credits = int(row[1])
            #单行校验失败只记录原因，不中断其他合法行
            if not course_name:
                raise ValueError("课程名称不能为空")
            if not 1 <= credits <= 10:
                raise ValueError("学分必须在 1-10 之间")
            if course_name in existing_names or course_name in added_names:
                raise ValueError("课程名称已存在")
            #只有校验通过后才加入代写入列表
            course_list.append(Course(course_name=course_name, credits=credits))
            added_names.add(course_name)
        except (IndexError, TypeError, ValueError) as exc:
            fail_list.append(f"第{row_idx}行：{exc}")

    # 所有合法课程统一提交；并发重名由数据库唯一约束兜底。
    db.add_all(course_list)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="课程名称已存在") from None
    #操作日志只有才导入commit成功后才写入
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
