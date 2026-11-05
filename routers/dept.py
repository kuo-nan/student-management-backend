from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Dept, User
from schemas import DeptCreate, DeptResp, PageResult, ResponseModel
from utils import add_operation_log, get_current_admin, paginate

router = APIRouter(prefix="/dept", tags=["班级管理"])


@router.post("/dept", summary="新增班级", response_model=ResponseModel[DeptResp])
def add_dept(
    dept: DeptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if db.scalar(select(Dept.id).where(Dept.dept_name == dept.dept_name)):
        raise HTTPException(status_code=409, detail="班级名称已存在")
    db_dept = Dept(**dept.model_dump())
    db.add(db_dept)
    db.commit()
    db.refresh(db_dept)
    add_operation_log(
        db,
        current_user,
        "班级管理",
        "新增",
        f"新增班级：{db_dept.dept_name}(ID:{db_dept.id})",
    )
    return ResponseModel.success(data=db_dept, message="新增成功")


@router.get(
    "/list",
    summary="班级列表",
    response_model=ResponseModel[PageResult[DeptResp]],
)
def get_dept_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    stmt = select(Dept.id, Dept.dept_name).order_by(Dept.id.desc())
    return ResponseModel.success(data=paginate(db, stmt, page, page_size))
