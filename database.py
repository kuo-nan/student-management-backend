import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings

# 如果提供了完整 DATABASE_URL,就直接解析使用
# 测试环境通过他切换到内存 SQLite
if settings.database_url:
    SQLALCHEMY_DATABASE_URL = make_url(settings.database_url)
# 没有完整地址时，根据DB_*配置构造MySQL 连接
# 使用 URL.create 可以正确处理密码中的特殊字符
else:
    SQLALCHEMY_DATABASE_URL = URL.create(
        drivername="mysql+pymysql",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        query={"charset": "utf8mb4"},
    )

engine_options = {
    # Debug 模式下打印生成的SQL,方便学习调试
    "echo": settings.debug,
    # 从连接池去连接钱先检查连接是否有效
    # 避免 MySQL关闭空闲连接后继续使用旧连接
    "pool_pre_ping": True,
}

if SQLALCHEMY_DATABASE_URL.get_backend_name() == "sqlite":
    engine_options["connect_args"] = {"check_same_thread": False}
    if SQLALCHEMY_DATABASE_URL.database in (None, "", ":memory:"):
        # 测试使用内存数据库，因此需要StaticPool让多个线程共享同一个内存数据库
        engine_options["poolclass"] = StaticPool
else:
    # 连接池通常保留5个连接，高峰期最多额外创建10个临时连接
    engine_options.update(pool_size=5, max_overflow=10)
# 管理真实数据库连接和连接池
engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_options)

# 创建Session的工厂
SessionLocal = sessionmaker(
    autocommit=False,  # 需要手动提交事务
    autoflush=False,  # 需要手动控制事务
    bind=engine,
)

# 所有ORM模型的元数据基类
Base = declarative_base()

#管理一次请求使用数据库Session
# FastAPI每次请求调用一次，’yield'前创建Session,请求结束后在finally中关闭
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 用于登录限流和统计缓存；设置较短超时，目的时Redis故障时快速失败并降级，不让主业务长时间阻塞
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    decode_responses=True,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
    health_check_interval=30,
    retry=Retry(NoBackoff(), 0),
    retry_on_error=[],
)
