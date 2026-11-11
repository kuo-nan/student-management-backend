from datetime import datetime
from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


#=== ORM Model ===
class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
#=================学生相关==================
#===新增学生请求体===
class StudentCreate(BaseModel):
    student_no:int=Field(ge=1, description="学号")
    name: str = Field(min_length=1, max_length=20, description="学生姓名")
    age: int = Field(ge=1, le=150, description="年龄")
    personal_score: int = Field(ge=0, le=100, description="学生个人评分")
    dept_id: int = Field(ge=1, description="班级ID")


StudentCrate = StudentCreate

#===修改学生请求体===
class StudentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=20)
    age: Optional[int] = Field(default=None, ge=1, le=150)
    personal_score: Optional[int] = Field(default=None, ge=0, le=100)
    dept_id: Optional[int] = Field(default=None, ge=1)

#===学生基础信息===
class StudentBase(ORMModel):
    student_no:int=Field(ge=1, description="学号")
    id: int
    name: str = Field(min_length=1, max_length=20)
    age: int
    personal_score: int = Field(ge=0, le=100)
    dept_id: int

#===学生响应信息===
class StudentResp(StudentBase):
    dept_name: Optional[str] = None

#=================班级相关==================
#===新增班级请求体===
class DeptCreate(BaseModel):
    dept_name: str = Field(min_length=1, max_length=20)

#===班级基础信息===
class DeptResp(ORMModel):
    id: int
    dept_name: str = Field(min_length=1, max_length=20)

#=================老师相关==================
#===新增老师请求体===
class TeacherCreate(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=20)

#===老师基础信息===
class TeacherResp(ORMModel):
    id: int
    name: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=20)

#=================课程相关==================
#===新增课程请求体===
class CourseCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=20)
    credits: int = Field(ge=1, le=10)

#===课程基础信息===
class CourseResp(ORMModel):
    id: int
    course_name: str = Field(min_length=1, max_length=20)
    credits: int = Field(ge=1, le=10)

#===老师课程信息===
class TeacherWithCoursesResp(TeacherResp):
    courses: List[CourseResp] = Field(default_factory=list)

#=================统计相关==================
#===老师课程统计信息===
class TeacherCourseStatResp(ORMModel):
    teacher_id: int = Field(ge=1)
    teacher_name: str
    course_count: int = Field(ge=0)
    student_count: int = Field(ge=0)

#===学生课程统计信息===
class StudentCourseStatResp(StudentResp):
    courses: List[CourseResp] = Field(default_factory=list)

#===班级统计信息===
class DeptStatResp(ORMModel):
    dept_name: str
    student_count: int = Field(ge=0)
    avg_personal_score: float

#=================请假相关==================
#===新增请假请求体===
class LeaveCreate(BaseModel):
    leave_type: str = Field(min_length=1, max_length=20)
    start_time: datetime
    end_time: datetime
    reason: str = Field(min_length=1, max_length=200)

#===请假审核信息===
class LeaveAudit(BaseModel):
    status: Literal["approved", "rejected"]
    audit_remark: Optional[str] = Field(default=None, max_length=255)

#===请假信息===
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

#=================用户相关==================
#===用户注册请求体===
class UserRegisterReq(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=32)

#===用户登录请求体===
class UserLoginReq(BaseModel):
    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=32)

#===学生账号创建请求体===
class StudentAccountCreate(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=32)
    student_id: int = Field(ge=1)

#===token响应信息===
class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"

#===用户修改密码请求体===
class ChangePasswordReq(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=32)

#===用户信息===
class UserResp(ORMModel):
    id: int
    username: str
    is_active: bool
    role: str

#===更新学生成绩请求体===
class UpdateScoreRep(BaseModel):
    student_id: int = Field(ge=1)
    course_id: int = Field(ge=1)
    score: int = Field(ge=0, le=100)

#=================考试相关==================
#===新增考试请求体===
class ExamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    exam_time: datetime
    remark: Optional[str] = Field(default=None, max_length=255)

#===修改考试请求体===
class ExamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    exam_time: Optional[datetime] = None
    remark: Optional[str] = Field(default=None, max_length=255)

#===考试信息===
class ExamInfo(ORMModel):
    id: int
    name: str
    exam_time: datetime
    remark: Optional[str] = None
    create_time: datetime

#===新增成绩请求体===
class ScoreCreate(BaseModel):
    exam_id: int = Field(ge=1)
    student_id: int = Field(ge=1)
    course_id: int = Field(ge=1)
    exam_score: int = Field(ge=0, le=100)

#===修改成绩请求体===
class ScoreUpdate(BaseModel):
    exam_score: int = Field(ge=0, le=100)

#===成绩信息===
class ScoreInfo(ORMModel):
    id: int
    exam_id: int
    student_id: int
    course_id: int
    exam_score: int
    create_time: datetime

#===成绩详情信息===
class ScoreDetailInfo(BaseModel):
    id: int
    exam_name: str
    student_name: str
    course_name: str
    exam_score: int
    create_time: datetime

#=================日志记录==================
#===操作日志信息===
class OperationLogResp(ORMModel):
    id: int
    user_id: int
    username: str
    module: str
    operation_type: str
    description: str
    created_at: datetime

T = TypeVar("T")

#===分页结果===
class PageResult(BaseModel, Generic[T]):
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    list: List[T]

#===统一响应结果===
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
