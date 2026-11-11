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

#=========================用户业务=============================
#带Depends的参数由FastAPI 在进入接口函数前解析
# get_db提供数据库Session; get_current_admin负责认证并校验角色

@router.post("/register", summary="注册普通学生账号", response_model=ResponseModel[UserResp])
def register(user: UserRegisterReq, db: Session = Depends(get_db)):
    #查询用户名是否已存在
    if db.scalar(select(User).where(User.username == user.username)):
        raise HTTPException(status_code=409, detail="用户名已被注册")
    #创建用户
    db_user = User(
        username=user.username,
        #数据库中只保存密码哈希，明文密码不会写入数据库
        password_hash=hash_password(user.password),
        role=UserRole.STUDENT.value,
    )
    db.add(db_user)
    try:
        db.commit()
    #两个相同的用户名的请求可能同时通过前面的查询
    # 最终只有一个能成功写入，另一个依靠数据库唯一约束被拦截
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
    # 先按客户端IP限流，在查询数据库和验证密码前拦截异常流量
    enforce_login_rate_limit(request)
    db_user = db.scalar(select(User).where(User.username == user.username))
    if not db_user or not verify_password(user.password, db_user.password_hash):
        # 用户不存在和密码错误使用相同提示，避免泄露某个用户名是否存在
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not db_user.is_active:
        #密码正确后还要检查账号是否启用
        # 被禁用账号不能继续获得新的 Token
        raise HTTPException(status_code=403, detail="账号已禁用，请联系管理员")
    # sub 保存用户ID,jwt.decode后会总payload["sub"]中取回
    access_token = create_access_token(data={"sub": str(db_user.id)})
    return ResponseModel.success(
        data={"access_token": access_token, "token_type": "bearer"}
    )

#此接口使用 OAuth2 表单格式，主要供Swagger 的Authorize按钮调用
# 因此不在公开APi文档中单独显示
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
        # sub 保存用户 ID:JWT的subject使用字符串更规范
        "access_token": create_access_token(data={"sub": str(db_user.id)}),
        "token_type": "bearer",
    }


@router.get("/me", summary="获取当前登录用户", response_model=ResponseModel[UserResp])
def get_my_info(current_user: User = Depends(get_current_user)):
    #current_user已由get_current_user解析并查询，接口无需再次查询
    return ResponseModel.success(data=current_user)


@router.post("/change_password", summary="修改当前用户密码", response_model=ResponseModel)
def change_password(
    req: ChangePasswordReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    #修改密码前必须验证旧密码，防止已登录会话直接替换密码
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return ResponseModel.success(message="密码修改成功")
    #当前系统使用无状态JWT，修改密码不会立刻让已经签发的Token失效
    #旧Token最多继续使用到exp过期



@router.post(
    "/user/student_account",
    summary="管理员为学生创建并绑定登录账号",
    response_model=ResponseModel[UserResp],
)
def create_student_account(
    req: StudentAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin), #只有管理员可以创建并绑定学生账号
):
    student = db.get(Student, req.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    if student.user_id is not None:
        # 一个学生最多绑定一个登录账号，已有user_id时直接拒绝
        raise HTTPException(status_code=409, detail="该学生已绑定登录账号")
    if db.scalar(select(User).where(User.username == req.username)):
        raise HTTPException(status_code=409, detail="用户名已被注册")

    db_user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role=UserRole.STUDENT.value,
    )
    #add 只是把User放进Session,没有真正执行 INSERT
    db.add(db_user)
    try:
        #flush会执行INSERT并取得自增ID,但不会提交事务
        # 之后才能使用db_user.id 绑定Student.user_id
        db.flush()
        student.user_id = db_user.id
        #User和Student的修改在同一个事务中一起提交
        db.commit()
    except IntegrityError:
        #任意一步失败都会回滚整个事务
        #避免出现账号创建成功但Student没有完成绑定的半成品数据
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
    #查询公开字段，绝对不能返回password_hash
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
        #不允许管理员禁用自己的账号，避免误操作后无法继续管理
        raise HTTPException(status_code=400, detail="不能禁用当前登录用户")
    #is_active被修改后,下一次请求中的get_current_user会读取最新的状态
    #因此已签发的Token也会立即失去访问权限
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
    #参数使用Body(...),因此Swagger中需要提交一个JSON字符串
    #而不是{"new_password":"..."}这样的对象
    new_password: str = Body(..., min_length=8, max_length=32),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    #重置密码只更新哈希：已有JWT不会被立刻撤销
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
        #删除登录账号前先解除 Student.user_id绑定
        user.student.user_id = None
    #删除前保存用户名，因为commit后user对象就不存在了
    username = user.username
    # 保留学生业务数据，不连带删除学生本人
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
