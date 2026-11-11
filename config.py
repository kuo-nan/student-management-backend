from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """加载应用配置，

    优先级：当前进程的环境变量>.env文件>这里的这里的默认值
    Docker Compose通过environment 注入的DB_HOST、REDIS_HOST等
    会覆盖.env中的本地配置
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore", # 允许.env中存在MYSQL_IMAGE等不由Settings声名的变量，不因额外字段启动失败
    )

    app_name: str = "学生管理系统"
    debug: bool = False
    port: int = 8000

    database_url: str | None = None  #完整数据库连接地址；存在时优先使用，测试环境会把它设置成SQLite
   # db:没有database_url时，用这些字段拼接MySQL地址。Docker就是Compose中的服务名
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "student1"

    # redis_*:登录限流和统计缓存使用的Redis地址和数据库编号
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    jwt_secret: str = "change-me-in-production"  # JWT签名密钥；修改后，旧的Token全部失败
    jwt_expires_minutes: int = 1440  #Token有效时间，当前默认1440分钟，也就是24小时

    # 非Debug环境禁止使用示例密钥，防止生产部署时忘记修改
    @model_validator(mode="after")
    def validate_production_secrets(self):
        insecure_secrets = {
            "change-me-in-production",
            "replace-this-before-deployment",
            "replace-with-a-long-random-secret",
        }
        if not self.debug and self.jwt_secret in insecure_secrets:
            raise ValueError("生产环境必须通过 JWT_SECRET 配置独立密钥")
        return self

settings = Settings()  # 应用启动时只加载一次，其他模块共享这个实例
