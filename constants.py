from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    STUDENT = "student"


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ErrorCode:
    SUCCESS = 200

    PARAM_VALID_ERROR = 40001
    BUSINESS_ERROR = 40002

    NOT_LOGIN = 40101
    ACCOUNT_DISABLED = 40301
    PERMISSION_DENIED = 40302
    TOO_MANY_REQUESTS = 42901

    DATA_NOT_FOUND = 40401

    DATABASE_ERROR = 50001
    SYSTEM_ERROR = 50000
