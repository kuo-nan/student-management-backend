from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from constants import UserRole
from database import get_db
from models import Student, User
from schemas import (
    ChangePasswordReq,
    PageResult,
    ResponseModel,
    StudentAccountCreate,
    TokenResp,
    UserLoginReq,
    UserRegisterReq,
    UserResp,
)
from utils import (
    add_operation_log,
    create_access_token,
    enforce_login_rate_limit,
    get_current_admin,
    get_current_user,
    hash_password,
    paginate,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", summary="注册普通学生账号", response_model=ResponseModel[UserResp])
def register(user: UserRegisterReq, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == user.username)):
        raise HTTPException(status_code=409, detail="用户名已被注册")

    db_user = User(
        username=user.username,
        password_hash=hash_password(user.password),
        role=UserRole.STUDENT.value,
    )
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已被注册") from None
    db.refresh(db_user)
    return ResponseModel.success(data=db_user, message="注册成功，请等待绑定学生信息")


@router.post("/login", summary="用户登录", response_model=ResponseModel[TokenResp])
def login(
    request: Request,
    user: UserLoginReq,
    db: Session = Depends(get_db),
):
    enforce_login_rate_limit(request)
    db_user = db.scalar(select(User).where(User.username == user.username))
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not db_user.is_active:
        raise HTTPException(status_code=403, detail="账号已禁用，请联系管理员")

    access_token = create_access_token(data={"sub": str(db_user.id)})
    return ResponseModel.success(
        data={"access_token": access_token, "token_type": "bearer"}
    )


@router.post("/oauth2/token", include_in_schema=False)
def oauth2_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    enforce_login_rate_limit(request)
    db_user = db.scalar(select(User).where(User.username == form_data.username))
    if not db_user or not verify_password(form_data.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not db_user.is_active:
        raise HTTPException(status_code=403, detail="账号已禁用，请联系管理员")
    return {
        "access_token": create_access_token(data={"sub": str(db_user.id)}),
        "token_type": "bearer",
    }


@router.get("/me", summary="获取当前登录用户", response_model=ResponseModel[UserResp])
def get_my_info(current_user: User = Depends(get_current_user)):
    return ResponseModel.success(data=current_user)


@router.post("/change_password", summary="修改当前用户密码", response_model=ResponseModel)
def change_password(
    req: ChangePasswordReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return ResponseModel.success(message="密码修改成功")


@router.post(
    "/user/student_account",
    summary="管理员为学生创建并绑定登录账号",
    response_model=ResponseModel[UserResp],
)
def create_student_account(
    req: StudentAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    student = db.get(Student, req.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    if student.user_id is not None:
        raise HTTPException(status_code=409, detail="该学生已绑定登录账号")
    if db.scalar(select(User).where(User.username == req.username)):
        raise HTTPException(status_code=409, detail="用户名已被注册")

    db_user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role=UserRole.STUDENT.value,
    )
    db.add(db_user)
    try:
        db.flush()
        student.user_id = db_user.id
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="账号或学生绑定已存在") from None
    db.refresh(db_user)
    add_operation_log(
        db,
        current_user,
        "用户管理",
        "创建学生账号",
        f"为学生 {student.name}(ID:{student.id}) 创建账号 {db_user.username}",
    )
    return ResponseModel.success(data=db_user, message="学生账号创建成功")


@router.get(
    "/user/list",
    summary="用户列表",
    response_model=ResponseModel[PageResult[UserResp]],
)
def get_user_list(
    username: str | None = Query(default=None, max_length=20),
    role: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    base_stmt = select(User.id, User.username, User.role, User.is_active).order_by(
        User.id.desc()
    )
    if username:
        base_stmt = base_stmt.where(User.username.like(f"%{username}%"))
    if role:
        base_stmt = base_stmt.where(User.role == role)
    result = paginate(db, base_stmt, page, page_size)
    return ResponseModel.success(data=result)


@router.put(
    "/user/toggle_active/{user_id}",
    summary="启用或禁用账号",
    response_model=ResponseModel,
)
def toggle_user_active(
    user_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能禁用当前登录用户")

    user.is_active = not user.is_active
    db.commit()
    status_text = "启用" if user.is_active else "禁用"
    add_operation_log(
        db,
        current_user,
        "用户管理",
        status_text,
        f"{status_text}用户账号：{user.username}(ID:{user.id})",
    )
    return ResponseModel.success(message=f"账号已{status_text}")


@router.post(
    "/user/reset_password/{user_id}",
    summary="管理员重置用户密码",
    response_model=ResponseModel,
)
def reset_user_password(
    user_id: int = Path(ge=1),
    new_password: str = Body(..., min_length=8, max_length=32),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(new_password)
    db.commit()
    add_operation_log(
        db,
        current_user,
        "用户管理",
        "重置密码",
        f"重置用户密码：{user.username}(ID:{user.id})",
    )
    return ResponseModel.success(message="密码重置成功")


@router.delete(
    "/user/{user_id}",
    summary="删除用户账号",
    response_model=ResponseModel,
)
def delete_user(
    user_id: int = Path(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")

    if user.student:
        user.student.user_id = None
    username = user.username
    db.delete(user)
    db.commit()
    add_operation_log(
        db,
        current_user,
        "用户管理",
        "删除",
        f"删除用户账号：{username}(ID:{user_id})",
    )
    return ResponseModel.success(message="删除成功")
