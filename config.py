from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "学生管理系统"
    debug: bool = False
    port: int = 8000

    database_url: str | None = None
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "student1"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    jwt_secret: str = "change-me-in-production"
    jwt_expires_minutes: int = 1440

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


settings = Settings()
