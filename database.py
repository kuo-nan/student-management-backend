import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings

if settings.database_url:
    SQLALCHEMY_DATABASE_URL = make_url(settings.database_url)
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
    "echo": settings.debug,
    "pool_pre_ping": True,
}
if SQLALCHEMY_DATABASE_URL.get_backend_name() == "sqlite":
    engine_options["connect_args"] = {"check_same_thread": False}
    if SQLALCHEMY_DATABASE_URL.database in (None, "", ":memory:"):
        engine_options["poolclass"] = StaticPool
else:
    engine_options.update(pool_size=5, max_overflow=10)

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_options)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
