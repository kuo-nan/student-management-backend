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


def paginate(db: Session, base_stmt, page: int, page_size: int) -> PageResult[T]:
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0
    offset = (page - 1) * page_size
    rows = db.execute(base_stmt.offset(offset).limit(page_size)).all()
    data_list = [row[0] if len(row) == 1 else row._asdict() for row in rows]
    return PageResult(total=total, page=page, page_size=page_size, list=data_list)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_expires_minutes


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = data.copy()
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/oauth2/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效登录凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = int(subject)
    except (JWTError, TypeError, ValueError):
        raise credentials_exception from None

    user = db.get(User, user_id)
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已禁用，请联系管理员",
        )
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员身份",
        )
    return current_user


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


def enforce_login_rate_limit(request: Request, limit: int = 10) -> None:
    global _redis_retry_after
    if time.monotonic() < _redis_retry_after:
        return
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"rate:login:{client_ip}"
    try:
        count = redis_client.incr(rate_key)
        if count == 1:
            redis_client.expire(rate_key, 60)#60秒后删除计数
    except RedisError:
        _redis_retry_after = time.monotonic() + 30
        logger.warning("Redis 不可用，登录限流临时降级")
        return
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录请求过于频繁，请一分钟后再试",
        )


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
