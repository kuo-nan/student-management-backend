"""考试和考试成绩的查询，新增与修改逻辑。"""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Course, Exam, ExamScore, Student, student_course
from schemas import ExamCreate, ExamUpdate, ScoreCreate, ScoreUpdate
from utils import paginate


def create_exam(db: Session, data: ExamCreate):
    #预查询用于尽早返回友好提示
    #真正的并发唯一性由Exam.name的数据库唯一约束保证
    if db.scalar(select(Exam.id).where(Exam.name == data.name)):
        raise ValueError("考试名称已存在")

    db_exam = Exam(**data.model_dump())
    db.add(db_exam)
   #两个管理员同时创建同名考试时,只有一个INSERT能成功
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("考试名称已存在") from None
    db.refresh(db_exam)
    return db_exam


def get_exam_page(
    db: Session,
    page: int,
    page_size: int,
    name: str | None = None,
):
    #按考试时间倒叙，最近的考试排前面
    query = select(Exam).order_by(Exam.exam_time.desc())
    #name使用包含匹配，只有传入关键子时才添加筛选条件
    if name:
        query = query.where(Exam.name.like(f"%{name}%"))
    return paginate(db, query, page, page_size)


def update_exam(db: Session, exam_id: int, data: ExamUpdate):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise ValueError("考试不存在")
    #使用exclude_unset支持只修改名称，时间备注中的一部分
    updates = data.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] != exam.name:
        duplicate = db.scalar(
            select(Exam.id).where(
                Exam.name == updates["name"],
                #修改考试名称时排除当前考试本身
                #否则名称没有变化也会被误判为重复
                Exam.id != exam_id,
            )
        )
        if duplicate:
            raise ValueError("考试名称已存在")
    for key, value in updates.items():
        setattr(exam, key, value)
    try:
        db.commit()
    #预查询和真正执行UPDATE之间仍有并发窗口
    #最终仍由数据库唯一约束兜底
    except IntegrityError:
        db.rollback()
        raise ValueError("考试名称已存在") from None
    db.refresh(exam)
    return exam


def delete_exam(db: Session, exam_id: int):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise ValueError("考试不存在")
    score_count = db.scalar(
        #先count是为了返回明确的业务错误
        #如果没有这层检查，数据库外键约束会产生更难理解的错误
        select(func.count())
        .select_from(ExamScore)
        .where(ExamScore.exam_id == exam_id)
    )
    #已有成绩的考试不允许删除，避免成绩记录失去所属考试
    if score_count:
        raise ValueError("该考试已有成绩，无法删除")
    db.delete(exam)
    db.commit()


def create_score(db: Session, data: ScoreCreate):
    #依次检查成绩关联的三个实体，避免写入无效外键
    if not db.get(Exam, data.exam_id):
        raise ValueError("考试不存在")
    if not db.get(Student, data.student_id):
        raise ValueError("学生不存在")
    if not db.get(Course, data.course_id):
        raise ValueError("课程不存在")
    #成绩必须对应一条真实选课关系
    #不能给未选修该课程的学生录入该课程成绩
    enrolled = db.scalar(
        select(student_course.c.student_id).where(
            #student_course是学生和课程的多对多中间表
            student_course.c.student_id == data.student_id,
            student_course.c.course_id == data.course_id,
        )
    )
    #查询到记录才表示选课关系存在
    if enrolled is None:
        raise ValueError("该学生未选择此课程，不能录入成绩")
    #ScoreCreate已通过Pydantic保证exam_score在0到100之间
    db_score = ExamScore(**data.model_dump())
    # 数据库唯一性约束保证
    # （exam_id,student_id,course_id)三者组合不能重复
    db.add(db_score)
    try:
        db.commit()
    #并发录入相同成绩时，只有一个请求成功
    #其余请求出发IntegrityError，并回滚失败事务
    except IntegrityError:
        db.rollback()
        #同一成绩已经存在应修改原纪录，而不是再次录入
        raise ValueError("该学生本次考试该课程已有成绩，请修改而非重复录入") from None
    db.refresh(db_score)
    return db_score


def get_score_page(
    db: Session,
    page: int,
    page_size: int,
    exam_id: int | None = None,
    student_id: int | None = None,
    course_id: int | None = None,
):
    query = select(ExamScore).order_by(ExamScore.create_time.desc())
    #管理员可以按考试、学生、课程任意组合筛选成绩
    if exam_id:
        query = query.where(ExamScore.exam_id == exam_id)
    if student_id:
        query = query.where(ExamScore.student_id == student_id)
    if course_id:
        query = query.where(ExamScore.course_id == course_id)
    return paginate(db, query, page, page_size)


def update_score(db: Session, score_id: int, data: ScoreUpdate):
    score = db.get(ExamScore, score_id)
    if not score:
        raise ValueError("成绩记录不存在")
    # 修改成绩只允许更新分数，不允许更换考试、学生或课程
    score.exam_score = data.exam_score
    db.commit()
    #refresh读取数据库中的最终只，确保响应与数据库一致
    db.refresh(score)
    return score


def get_my_score(
    db: Session,
    #student_id 来自当前登录学生的绑定关系，不接受客户端传入
    student_id: int,
    page: int,
    page_size: int,
):
    query = (
        select(ExamScore)
        .where(ExamScore.student_id == student_id)
        .order_by(ExamScore.create_time.desc())
    )
    return paginate(db, query, page, page_size)
