"""学生查询、新增和修改的数据库业务逻辑"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Dept, Student
from schemas import StudentCrate, StudentUpdate
from utils import paginate


def get_student_page(
    db: Session,
    page: int,
    page_size: int,
    student_no: int | None = None,
    name: str | None = None,
):
    query = (
        select(
            Student.student_no,
            Student.id,
            Student.name,
            Student.age,
            Student.personal_score,
            Student.dept_id,
            Dept.dept_name,
        )
        #显示选择响应需要的字段，并左连接Dept获取班级名称
        .join(Dept, Student.dept_id == Dept.id, isouter=True)
        .order_by(Student.id.desc())
    )
    #只有客户端提供搜素条件时才追加WHERE，避免空字符串导致错误过滤
    if student_no:
        query = query.where(Student.student_no == student_no)
    if name:
        #like(f"%{name}%")  表示姓名中包含改关键字即可匹配
        query = query.where(Student.name.like(f"%{name}%"))
    #paginate 负责总数，offest和limit
    return paginate(db, query, page, page_size)


def create_student(
    db: Session,
    #data已由StudentCreate校验过
    data: StudentCrate
):
    #model_dump将请求模型转换成Student 构造参数
    student = Student(**data.model_dump())
    #add 只是把对象放进Session,commit才会执行真正的INSERT
    db.add(student)
    try:
        db.commit()
    #学号的唯一性最终由数据库约束保证
    #即使两个并发请求通过前面的查询，也只有一个能成功
    except IntegrityError as exc:
        db.rollback()
        if "student_no" in str(exc.orig).lower():
            raise ValueError("学号已存在") from None
        #如果错误不是学号重复，就继续抛出，交给全局数据库异常处理器
        raise
    #refresh读取数据库生成的自增id和服务端默认值
    db.refresh(student)
    return student


def update_student_service(
    db: Session,
    student_id: int,
    data: StudentUpdate,
):
    student = db.get(Student, student_id)
    if not student:
        raise ValueError("学生不存在")
    #只更新客户端明确提交的字段
    #exclude_unset=True 可以避免未提交字段被None或默认值覆盖
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(student, key, value)
    db.commit()
    db.refresh(student)
    return student
