import time
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from constants import UserRole
from database import get_db, redis_client
from logger import logger
from models import OperationLog, Student, User
from schemas import PageResult

T = TypeVar("T")
_redis_retry_after = 0.0

#===========分页=============
def paginate(db: Session, base_stmt, page: int, page_size: int) -> PageResult[T]:
    # 统计总数，用同一个查询构造COUNT,确保搜索条件和分页数据一致
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    # 统计共有多少条数据
    total = db.execute(count_stmt).scalar() or 0
    # 计算偏移量
    # 第1页offset为0：以后每页跳过钱买你已经展示的数据
    offset = (page - 1) * page_size
    # 获取分页数据
    rows = db.execute(base_stmt.offset(offset).limit(page_size)).all()
    # 将结果转换为列表
    #单字段查询返回 row[0]，多字段查询转换为字典
    data_list = [row[0] if len(row) == 1 else row._asdict() for row in rows]
    # 返回分页结果
    return PageResult(total=total, page=page, page_size=page_size, list=data_list)  


#===========认证=============
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_expires_minutes

# 生成不可逆的bcrypt密码哈希
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# 校验明文密码是否与已保存的哈希匹配，不是解密哈希
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# 创建访问令牌
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    # iot和exp 使用UTC时间，避免不同部署时区导致Token失效时间混乱
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    # 复用调用方数据，避免修改调用方传进来的字典
    to_encode = data.copy()
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/oauth2/token")

# 获取当前用户
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """解析并验证JWT,查询用户，再检查账号是否处于启用状态。"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效登录凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # decode 会验证签名和exp：签名错误或Token 过期都会抛出 JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        # payload中的值时 JSON数据：转换失败也属于无效凭证
        user_id = int(subject)
    except (JWTError, TypeError, ValueError):
        raise credentials_exception from None

    user = db.get(User, user_id) # 根据用户ID获取用户信息
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已禁用，请联系管理员",
        )
    return user

#===========权限和限流=============
# get_current_admin和get_current_student 是在get_current_user完成身份后，再检查角色
# 获取当前管理员用户
def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员身份",
        )
    return current_user

# 获取当前学生用户
def get_current_student(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Student:
    if current_user.role != UserRole.STUDENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该接口仅限学生账号使用",
        )
    student = db.scalar(select(Student).where(Student.user_id == current_user.id))
    if not student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号尚未绑定学生信息",
        )
    return student

# 登录限流
def enforce_login_rate_limit(request: Request, limit: int = 10) -> None:
    global _redis_retry_after
    if time.monotonic() < _redis_retry_after:
        return
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"rate:login:{client_ip}"
    try:
        # incr是原子自增，并发请求不会出现先读后写导致少计数
        count = redis_client.incr(rate_key)
        # 只在计数从0变成1 时设置60秒有效期
        # 避免每次登录都续期，导致窗口永远无法结束
        if count == 1:
            redis_client.expire(rate_key, 60)#60秒后删除计数
    # 如果Redis故障时暂时跳过限流，优先保证登录功能可用
    except RedisError:
        _redis_retry_after = time.monotonic() + 30
        logger.warning("Redis 不可用，登录限流临时降级")
        return
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录请求过于频繁，请一分钟后再试",
        )

# 添加操作日志
# 操作日志时辅助功能，写入失败是回滚日志事物
# 但不让异常影响已经完成的的主业务
def add_operation_log(
    db: Session,
    current_user: User,
    module: str,
    operation_type: str,
    description: str,
) -> None:
    try:
        db.add(
            OperationLog(
                user_id=current_user.id,
                username=current_user.username,
                module=module,
                operation_type=operation_type,
                description=description,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("写入操作日志失败")
