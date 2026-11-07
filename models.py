from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from constants import LeaveStatus, UserRole
from database import Base

student_course = Table(
    "student_course",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("student.id"), primary_key=True),
    Column("course_id", Integer, ForeignKey("course.id"), primary_key=True),
    Column("score", Integer, nullable=True, comment="课程成绩：0-100分"),
)

teacher_course = Table(
    "teacher_course",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("course.id"), primary_key=True),
    Column("teacher_id", Integer, ForeignKey("teacher.id"), primary_key=True),
)

teacher_dept = Table(
    "teacher_dept",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teacher.id"), primary_key=True),
    Column("dept_id", Integer, ForeignKey("dept.id"), primary_key=True),
)


class Dept(Base):
    __tablename__ = "dept"

    id = Column(Integer, primary_key=True)
    dept_name = Column(String(20), nullable=False)
    students = relationship("Student", back_populates="dept")
    teachers = relationship("Teacher", secondary=teacher_dept, back_populates="depts")


class Student(Base):
    __tablename__ = "student"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), unique=True)
    name = Column(String(20), nullable=False)
    age = Column(Integer, default=0)
    score = Column(Integer, nullable=False)
    dept_id = Column(Integer, ForeignKey("dept.id"))
    dept = relationship("Dept", back_populates="students")
    user = relationship("User", back_populates="student", uselist=False)
    courses = relationship(
        "Course",
        secondary=student_course,
        back_populates="students",
        primaryjoin="Student.id==student_course.c.student_id",
        secondaryjoin="Course.id==student_course.c.course_id",
    )


class Course(Base):
    __tablename__ = "course"

    id = Column(Integer, primary_key=True)
    course_name = Column(String(20), nullable=False)
    credits = Column(Integer, nullable=False)
    students = relationship(
        "Student",
        secondary=student_course,
        back_populates="courses",
        primaryjoin="Course.id==student_course.c.course_id",
        secondaryjoin="Student.id==student_course.c.student_id",
    )
    teachers = relationship("Teacher", secondary=teacher_course, back_populates="courses")


class Teacher(Base):
    __tablename__ = "teacher"

    id = Column(Integer, primary_key=True)
    name = Column(String(20), nullable=False)
    title = Column(String(20), nullable=False)
    courses = relationship("Course", secondary=teacher_course, back_populates="teachers")
    depts = relationship("Dept", secondary=teacher_dept, back_populates="teachers")


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, comment="用户ID")
    username = Column(String(20), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="加密后的密码")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    role = Column(
        String(20),
        default=UserRole.STUDENT.value,
        nullable=False,
        comment="角色：student=学生 admin=管理员",
    )
    student = relationship("Student", back_populates="user", uselist=False)


class StudentLeave(Base):
    __tablename__ = "student_leave"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="请假ID")
    student_id = Column(
        Integer, ForeignKey("student.id"), nullable=False, comment="学生ID"
    )
    leave_type = Column(String(20), nullable=False, comment="请假类型")
    start_time = Column(DateTime, nullable=False, comment="开始时间")
    end_time = Column(DateTime, nullable=False, comment="结束时间")
    reason = Column(String(255), nullable=False, comment="请假原因")
    status = Column(
        String(20),
        default=LeaveStatus.PENDING.value,
        nullable=False,
        comment="状态：pending/approved/rejected",
    )
    audit_remark = Column(String(255), comment="审批备注")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")
    update_time = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
    student = relationship("Student", backref="leaves")


class Exam(Base):
    __tablename__ = "exam"
    __table_args__ = (UniqueConstraint("name", name="uk_exam_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="考试ID")
    name = Column(String(50), nullable=False, comment="考试名称")
    exam_time = Column(DateTime, nullable=False, comment="考试时间")
    remark = Column(String(255), comment="备注")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")


class ExamScore(Base):
    __tablename__ = "exam_score"
    __table_args__ = (
        UniqueConstraint(
            "exam_id", "student_id", "course_id", name="uk_exam_student_course"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="学生成绩ID")
    exam_id = Column(Integer, ForeignKey("exam.id"), nullable=False, comment="考试ID")
    student_id = Column(
        Integer, ForeignKey("student.id"), nullable=False, comment="学生ID"
    )
    course_id = Column(
        Integer, ForeignKey("course.id"), nullable=False, comment="课程ID"
    )
    exam_score = Column(Integer, nullable=False, comment="分数")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")
    update_time = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
    exam = relationship("Exam", backref="scores")
    student = relationship("Student", backref="exam_scores")
    course = relationship("Course", backref="exam_scores")


class OperationLog(Base):
    __tablename__ = "operation_log"

    id = Column(Integer, primary_key=True, comment="日志ID")
    user_id = Column(Integer, nullable=False, comment="操作人ID")
    username = Column(String(20), nullable=False, comment="操作人用户名")
    module = Column(String(30), nullable=False, comment="操作模块")
    operation_type = Column(String(20), nullable=False, comment="操作类型")
    description = Column(String(255), nullable=False, comment="操作描述")
    created_at = Column(DateTime, default=datetime.now, comment="操作时间")
