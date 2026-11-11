from enum import Enum


#用户角色
class UserRole(str, Enum):
    ADMIN = "admin"
    STUDENT = "student"

#请假状态
class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

# ErrorCode是业务码，不是HTTP状态码
# 例如：HTTP401的响应体里可以有业务码40101
class ErrorCode:
    SUCCESS = 200  # 响应体中业务成功码
    # 参数校验失败，由全局校验异常处理器返回，HTTP状态为422
    PARAM_VALID_ERROR = 40001
    # 一般业务规则不满足,对应HTTP 400
    BUSINESS_ERROR = 40002
    #请求中没有有效JWT、JWT过期，或登录凭证错误
    NOT_LOGIN = 40101
    #账号被禁用专用业务码
    #由BusinessHTTPException显式携带，不会和普通权限不足混淆
    ACCOUNT_DISABLED = 40301
    #已登录但角色权限不足，例如学生访问管理员接口
    PERMISSION_DENIED = 40302
    # 登录频率超过限制，对应HTTP 429
    TOO_MANY_REQUESTS = 42901
    # 要查询或操作的数不存在，对应HTTP 404
    DATA_NOT_FOUND = 40401
    # SQLAlchemy 数据库操作异常，对应HTTP 500
    DATABASE_ERROR = 50001
    # 未预料到的服务端异常，对应HTTP 500
    SYSTEM_ERROR = 50000
