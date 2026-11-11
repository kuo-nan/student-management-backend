"""班级的新增和分页查询接口。（只有管理员有权操作）"""
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
    #预查询用于尽早提示重名
    #注意：当前dept_name没有数据库唯一约束，因此预查询不能完全防止并发创建两个同名班级
    if db.scalar(select(Dept.id).where(Dept.dept_name == dept.dept_name)):
        raise HTTPException(status_code=409, detail="班级名称已存在")
    #model_dump将DeptCreate的请求字段转换成Dept构造参数
    db_dept = Dept(**dept.model_dump())
    #add 将对象放进Session,commit才会实际写入数据库
    db.add(db_dept)
    db.commit()
    #refresh获取数据库生成的自增ID
    db.refresh(db_dept)
    #操作日志在业务数据提交后单独写入，日志失败不会撤销班级创建
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
    #只查询分页需要公开字段，不直接返回ORM对象
    stmt = select(Dept.id, Dept.dept_name).order_by(Dept.id.desc())
    #paginate统一处理总数、offset和limit
    return ResponseModel.success(data=paginate(db, stmt, page, page_size))
