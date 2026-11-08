from datetime import datetime
from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StudentCreate(BaseModel):
    student_no:int=Field(ge=1, description="学号")
    name: str = Field(min_length=1, max_length=20, description="学生姓名")
    age: int = Field(ge=1, le=150, description="年龄")
    personal_score: int = Field(ge=0, le=100, description="学生个人评分")
    dept_id: int = Field(ge=1, description="班级ID")


StudentCrate = StudentCreate


class StudentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=20)
    age: Optional[int] = Field(default=None, ge=1, le=150)
    personal_score: Optional[int] = Field(default=None, ge=0, le=100)
    dept_id: Optional[int] = Field(default=None, ge=1)


class StudentBase(ORMModel):
    student_no:int=Field(ge=1, description="学号")
    id: int
    name: str = Field(min_length=1, max_length=20)
    age: int
    personal_score: int = Field(ge=0, le=100)
    dept_id: int


class StudentResp(StudentBase):
    dept_name: Optional[str] = None


class DeptCreate(BaseModel):
    dept_name: str = Field(min_length=1, max_length=20)


class DeptResp(ORMModel):
    id: int
    dept_name: str = Field(min_length=1, max_length=20)


class TeacherCreate(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=20)


class TeacherResp(ORMModel):
    id: int
    name: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=20)


class CourseCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=20)
    credits: int = Field(ge=1, le=10)


class CourseResp(ORMModel):
    id: int
    course_name: str = Field(min_length=1, max_length=20)
    credits: int = Field(ge=1, le=10)


class TeacherWithCoursesResp(TeacherResp):
    courses: List[CourseResp] = Field(default_factory=list)


class TeacherCourseStatResp(ORMModel):
    teacher_id: int = Field(ge=1)
    teacher_name: str
    course_count: int = Field(ge=0)
    student_count: int = Field(ge=0)


class StudentCourseStatResp(StudentResp):
    courses: List[CourseResp] = Field(default_factory=list)


class DeptStatResp(ORMModel):
    dept_name: str
    student_count: int = Field(ge=0)
    avg_personal_score: float


class LeaveCreate(BaseModel):
    leave_type: str = Field(min_length=1, max_length=20)
    start_time: datetime
    end_time: datetime
    reason: str = Field(min_length=1, max_length=200)


class LeaveAudit(BaseModel):
    status: Literal["approved", "rejected"]
    audit_remark: Optional[str] = Field(default=None, max_length=255)


class LeaveInfo(ORMModel):
    id: int
    student_id: int
    leave_type: str
    start_time: datetime
    end_time: datetime
    reason: str
    status: Literal["pending", "approved", "rejected"]
    audit_remark: Optional[str] = None
    create_time: datetime
    update_time: Optional[datetime] = None


class UserRegisterReq(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=32)


class UserLoginReq(BaseModel):
    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=32)


class StudentAccountCreate(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=32)
    student_id: int = Field(ge=1)


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordReq(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=32)


class UserResp(ORMModel):
    id: int
    username: str
    is_active: bool
    role: str


class UpdateScoreRep(BaseModel):
    student_id: int = Field(ge=1)
    course_id: int = Field(ge=1)
    score: int = Field(ge=0, le=100)


class OperationLogResp(ORMModel):
    id: int
    user_id: int
    username: str
    module: str
    operation_type: str
    description: str
    created_at: datetime


class ExamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    exam_time: datetime
    remark: Optional[str] = Field(default=None, max_length=255)


class ExamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    exam_time: Optional[datetime] = None
    remark: Optional[str] = Field(default=None, max_length=255)


class ExamInfo(ORMModel):
    id: int
    name: str
    exam_time: datetime
    remark: Optional[str] = None
    create_time: datetime


class ScoreCreate(BaseModel):
    exam_id: int = Field(ge=1)
    student_id: int = Field(ge=1)
    course_id: int = Field(ge=1)
    exam_score: int = Field(ge=0, le=100)


class ScoreUpdate(BaseModel):
    exam_score: int = Field(ge=0, le=100)


class ScoreInfo(ORMModel):
    id: int
    exam_id: int
    student_id: int
    course_id: int
    exam_score: int
    create_time: datetime


class ScoreDetailInfo(BaseModel):
    id: int
    exam_name: str
    student_name: str
    course_name: str
    exam_score: int
    create_time: datetime


T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    list: List[T]


class ResponseModel(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: Optional[T] = None

    @classmethod
    def success(cls, data: T | None = None, message: str = "success"):
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, code: int = 400, message: str = "bad request"):
        return cls(code=code, message=message, data=None)
