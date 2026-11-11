"""创建FastAPI应用，注册路由、中间建和全局异常处理器"""
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from config import settings
from constants import ErrorCode
from exceptions import BusinessHTTPException
from logger import logger
from routers import course, dept, exam, file, leave, log, stats, student, student_course, teacher
from routers.auth import router as auth_router

#这些元信息会显示在Swagger文档首页
app = FastAPI(
    title="学生管理系统接口",
    description="基于 FastAPI 的学生、教师、课程、选课、考试、成绩与请假管理系统",
    version="1.0.0",
)

upload_dir = Path("upload")
upload_dir.mkdir(parents=True, exist_ok=True)
#创建上传目录，并将/upload映射为静态文件访问路径
#上传文件使用UUID命名，避免客户端直接空值服务器文件路径
app.mount("/upload", StaticFiles(directory=upload_dir), name="upload")

#将各业务模块的APIRouter挂载到同一个FastAPI应用
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


# health 不访问数据库或 Redis，
# 用于确认 FastAPI 进程本身能够响应请求。
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

#========请求耗时中间件==========
@app.middleware("http")
async def log_requests(request: Request, call_next):
    #call_next之前的代码在进入接口前执行
    #call_next之后在响应生成后执行
    start_time = time.perf_counter()
    response = await call_next(request)
    #perf_counter适合测量经过时间，不受系统时间调整影响
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    # request.client 可能为空，因此使用 "-" 作为兜底值。
    client_ip = request.client.host if request.client else "-"
    # 这里写入的是应用日志，不会写入 operation_log 数据库表。
    logger.info(
        "%s %-6s %-40s %7sms client=%s",
        response.status_code,
        request.method,
        request.url.path,
        elapsed_ms,
        client_ip,
    )
    return response

#=======全局异常处理==============
# HTTP 状态码表示协议层结果；
# 响应体中的 code 表示系统业务码。
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code_map = {
        400: ErrorCode.BUSINESS_ERROR,
        401: ErrorCode.NOT_LOGIN,
        403: ErrorCode.PERMISSION_DENIED,
        404: ErrorCode.DATA_NOT_FOUND,
        429: ErrorCode.TOO_MANY_REQUESTS,
    }
    business_code = (
        exc.code
        if isinstance(exc, BusinessHTTPException)
        else code_map.get(exc.status_code, ErrorCode.SYSTEM_ERROR)
    )
    return JSONResponse(
        #根据HTTP状态码转换成项目同一业务码
        status_code=exc.status_code,
        content={
            "code": business_code,
            "message": exc.detail,
            "data": None,
        },
        #原异常中的响应头也要保留
        #例如401响应需要返回WWW-Authenticate:Bearer
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Pydantic 请求体校验失败时返回 HTTP 422，
    # 响应体业务码使用 PARAM_VALID_ERROR。
    return JSONResponse(
        status_code=422,
        content={
            "code": ErrorCode.PARAM_VALID_ERROR,
            "message": "请求参数校验失败",
            # exc.errors() 包含具体是哪个字段、因为什么校验规则失败。
            "data": exc.errors(),
        },
    )


@app.exception_handler(SQLAlchemyError)
async def db_exception_handler(request: Request, exc: SQLAlchemyError):
    #exc_info=exc 会将完整异常堆栈写入应用日志，便于排查数据库错误
    logger.error("数据库操作失败", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            # 对外只返回统一提示，不把数据库表名、SQL 或连接信息暴露给客户端。
            "code": ErrorCode.DATABASE_ERROR,
            "message": "数据库操作失败",
            "data": None,
        },
    )

# 这是最后的异常兜底，处理没有匹配到其他处理器的异常。
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("系统异常", exc_info=exc)
    # 记录完整堆栈，但客户端只得到通用 500 响应。
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
