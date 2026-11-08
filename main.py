import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from config import settings
from constants import ErrorCode
from logger import logger
from routers import course, dept, exam, file, leave, log, stats, student, student_course, teacher
from routers.auth import router as auth_router

app = FastAPI(
    title="学生管理系统接口",
    description="基于 FastAPI 的学生、教师、课程、选课、考试、成绩与请假管理系统",
    version="1.0.0",
)

upload_dir = Path("upload")
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/upload", StaticFiles(directory=upload_dir), name="upload")


#==============老师业务==================
app.include_router(teacher.router)
#==============学生业务==================
app.include_router(student.router)
#==============课程业务==================
app.include_router(course.router)
#==============统计业务==================
app.include_router(stats.router)
#==============班级业务==================
app.include_router(dept.router)
#==============选课业务==================
app.include_router(student_course.router)
#==============考试业务==================
app.include_router(exam.router)
#==============请假业务==================
app.include_router(leave.router)
#==============登录业务==================
app.include_router(auth_router)
#==============文件业务==================
app.include_router(file.router)
#==============日志业务==================
app.include_router(log.router)


@app.get("/", include_in_schema=False)
def index():
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["系统"])
def health_check():
    return {"status": "ok"}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    client_ip = request.client.host if request.client else "-"
    logger.info(
        "%s %-6s %-40s %7sms client=%s",
        response.status_code,
        request.method,
        request.url.path,
        elapsed_ms,
        client_ip,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code_map = {
        400: ErrorCode.BUSINESS_ERROR,
        401: ErrorCode.NOT_LOGIN,
        403: ErrorCode.PERMISSION_DENIED,
        404: ErrorCode.DATA_NOT_FOUND,
        429: ErrorCode.TOO_MANY_REQUESTS,
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code_map.get(exc.status_code, ErrorCode.SYSTEM_ERROR),
            "message": exc.detail,
            "data": None,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": ErrorCode.PARAM_VALID_ERROR,
            "message": "请求参数校验失败",
            "data": exc.errors(),
        },
    )


@app.exception_handler(SQLAlchemyError)
async def db_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error("数据库操作失败", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "code": ErrorCode.DATABASE_ERROR,
            "message": "数据库操作失败",
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("系统异常", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "code": ErrorCode.SYSTEM_ERROR,
            "message": "服务器内部错误",
            "data": None,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
    )
