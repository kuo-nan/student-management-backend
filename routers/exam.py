from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Student, User
from schemas import (
    ExamCreate,
    ExamInfo,
    ExamUpdate,
    PageResult,
    ResponseModel,
    ScoreCreate,
    ScoreInfo,
    ScoreUpdate,
)
from services.exam_service import (
    create_exam,
    create_score,
    delete_exam,
    get_exam_page,
    get_my_score,
    get_score_page,
    update_exam,
    update_score,
)
from utils import get_current_admin, get_current_student

router = APIRouter(prefix="/exam", tags=["考试与成绩"])

# 新增、修改删除考试：
# 考试管理只允许管理员操作。

#成绩录入和成绩列表：
# 管理员负责录入和查看所有学生成绩。
# 当前模块把 Service 抛出的 ValueError 统一转换为 HTTP 400。
# 如果后续需要更精确的状态码，可以引入 NotFound、Conflict 等业务异常类型。

@router.post("", summary="新增考试", response_model=ResponseModel[ExamInfo])
def add_exam(
    data: ExamCreate,
    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_admin),
):
    try:
        exam = create_exam(db, data)
        return ResponseModel.success(data=exam)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get(
    "/list",
    summary="考试列表",
    response_model=ResponseModel[PageResult[ExamInfo]],
)
def exam_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    name: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_admin),
):
    return ResponseModel.success(data=get_exam_page(db, page, page_size, name))


@router.put(
    "/{exam_id}",
    summary="编辑考试",
    response_model=ResponseModel[ExamInfo],
)
def edit_exam(
    data: ExamUpdate,
    exam_id: int = Path(ge=1),
    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_admin),
):
    try:
        return ResponseModel.success(data=update_exam(db, exam_id, data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete(
    "/{exam_id}",
    summary="删除考试",
    response_model=ResponseModel,
)
def remove_exam(
    exam_id: int = Path(ge=1),
    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_admin),
):
    try:
        delete_exam(db, exam_id)
        return ResponseModel.success(message="删除成功")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/score",
    summary="录入成绩",
    response_model=ResponseModel[ScoreInfo],
)
def add_score(
    data: ScoreCreate,
    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_admin),
):
    try:
        return ResponseModel.success(data=create_score(db, data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get(
    "/score/list",
    summary="成绩列表",
    response_model=ResponseModel[PageResult[ScoreInfo]],
)
def list_scores(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    exam_id: int | None = Query(default=None, ge=1),
    student_id: int | None = Query(default=None, ge=1),
    course_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    return ResponseModel.success(
        data=get_score_page(
            db,
            page,
            page_size,
            exam_id,
            student_id,
            course_id,
        )
    )


@router.put(
    "/score/{score_id}",
    summary="修改成绩",
    response_model=ResponseModel[ScoreInfo],
)
def edit_score(
    data: ScoreUpdate,
    score_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    try:
        return ResponseModel.success(data=update_score(db, score_id, data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get(
    "/score/my",
    summary="查看我的成绩",
    response_model=ResponseModel[PageResult[ScoreInfo]],
)
def my_score_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    # 学生只能通过 Token 对应的 Student.id 查询自己的成绩，
    # 无法通过修改请求参数查看其他学生。
    current_student: Student = Depends(get_current_student),
):
    page_data = get_my_score(db, current_student.id, page, page_size)
    return ResponseModel.success(data=page_data)
