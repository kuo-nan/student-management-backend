from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Student, User
from schemas import LeaveAudit, LeaveCreate, LeaveInfo, PageResult, ResponseModel
from services.leave_service import (
    audit_leave,
    cancel_leave,
    create_leaves,
    get_all_leaves,
    get_my_leaves,
)
from utils import get_current_admin, get_current_student

router = APIRouter(prefix="/leave", tags=["请假管理"])


@router.post("", summary="提交请假申请", response_model=ResponseModel[LeaveInfo])
def submit_leave(
    data: LeaveCreate,
    db: Session = Depends(get_db),
    current_student: Student = Depends(get_current_student),
):
    try:
        leave = create_leaves(db, current_student.id, data)
        return ResponseModel.success(data=leave)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get(
    "/my",
    summary="查看我的请假记录",
    response_model=ResponseModel[PageResult[LeaveInfo]],
)
def my_leave_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_student: Student = Depends(get_current_student),
):
    page_data = get_my_leaves(db, current_student.id, page, page_size)
    return ResponseModel.success(data=page_data)


@router.delete(
    "/{leave_id}",
    summary="撤销我的请假申请",
    response_model=ResponseModel,
)
def cancel_my_leave(
    leave_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_student: Student = Depends(get_current_student),
):
    try:
        cancel_leave(db, leave_id, current_student.id)
        return ResponseModel.success(message="撤销成功")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get(
    "/list",
    summary="管理员查看所有请假记录",
    response_model=ResponseModel[PageResult[LeaveInfo]],
)
def leave_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: str | None = Query(default=None),
    student_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    page_data = get_all_leaves(db, page, page_size, status, student_id)
    return ResponseModel.success(data=page_data)


@router.put(
    "/{leave_id}/audit",
    summary="管理员审批请假",
    response_model=ResponseModel[LeaveInfo],
)
def audit_leave_api(
    data: LeaveAudit,
    leave_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    try:
        leave = audit_leave(db, leave_id, data)
        return ResponseModel.success(data=leave)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
