"""管理员查询数据库操作审计日志的只读接口"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import OperationLog, User
from schemas import OperationLogResp, PageResult, ResponseModel
from utils import get_current_admin, paginate

router = APIRouter(prefix="/log", tags=["操作日志"])


@router.get(
    "/list",
    summary="查询操作日志",
    response_model=ResponseModel[PageResult[OperationLogResp]],
)
def get_log_list(
    username: str | None = Query(default=None, max_length=20),
    module: str | None = Query(default=None, max_length=30),
    operation_type: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    #操作日志包含用户名和管理动作，只允许管理员查看
    #该接口只读取operation_log表，不修改业务数据
    base_stmt = select(
        OperationLog.id,
        OperationLog.user_id,
        OperationLog.username,
        OperationLog.module,
        OperationLog.operation_type,
        OperationLog.description,
        OperationLog.created_at,
    ).order_by(OperationLog.created_at.desc()) #按创建时间倒序，最新操作显示在前面
    #用户名使用包含匹配，模块和操作类型使用精确匹配
    if username:
        base_stmt = base_stmt.where(OperationLog.username.like(f"%{username}%"))
    if module:
        base_stmt = base_stmt.where(OperationLog.module == module)
    if operation_type:
        base_stmt = base_stmt.where(OperationLog.operation_type == operation_type)
    return ResponseModel.success(data=paginate(db, base_stmt, page, page_size))
