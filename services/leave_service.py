"""处理请假申请、查询、原子审批和撤销的数据库逻辑"""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from constants import LeaveStatus
from models import Student, StudentLeave
from schemas import LeaveAudit, LeaveCreate
from utils import paginate


def create_leaves(db: Session, student_id: int, data: LeaveCreate):
    #请假时间必须有效，否则不允许创建申请
    if data.start_time >= data.end_time:
        raise ValueError("结束时间必须晚于开始时间")
    if not db.get(Student, student_id):
        raise ValueError("学生不存在")

    db_leave = StudentLeave(
        student_id=student_id,
        leave_type=data.leave_type,
        start_time=data.start_time,
        end_time=data.end_time,
        reason=data.reason,
        #新建申请统一从pending开始，客户端不能直接提交approved或rejected
        status=LeaveStatus.PENDING.value,
    )
    db.add(db_leave)
    #commit写库，refresh获取数据库生成的ID、默认状态和创建时间
    db.commit()
    db.refresh(db_leave)
    return db_leave


def get_my_leaves(
    db: Session,
    #由当前登录学生解析得到，不接受客户端传入
    student_id: int,
    page: int,
    page_size: int,
):
    query = (
        select(StudentLeave)
        .where(StudentLeave.student_id == student_id)
        #按创建时间倒序，让最新申请显示在列表前面
        .order_by(StudentLeave.create_time.desc())
    )
    return paginate(db, query, page, page_size)


def get_all_leaves(
    db: Session,
    page: int,
    page_size: int,
    status: str | None = None,
    student_id: int | None = None,
):
    query = select(StudentLeave).order_by(StudentLeave.create_time.desc())
    # 管理员可以按状态和学生筛选；没有提供条件时不追加WHERE
    if status:
        query = query.where(StudentLeave.status == status)
    if student_id:
        query = query.where(StudentLeave.student_id == student_id)
    return paginate(db, query, page, page_size)


def audit_leave(db: Session, leave_id: int, data: LeaveAudit):
    #把检查是否为pending和修改状态合并为一个原子UPDATE
    #两个管理员同时审批时，只有一个请求能真正修改成功
    result=db.execute(
        update(StudentLeave)
        .where(
            StudentLeave.id==leave_id,
            #只有仍处于pending的记录才能被更新
            StudentLeave.status=="pending",
        )
        .values(
                status=data.status,
                audit_remark=data.audit_remark
                )
    )
    #rowcount表示受到这条UPDATE影响的记录数
    #为0表示请假不存在，或者已经被其他请求审批
    if result.rowcount==0:
        # 没有更新任何记录时回滚当前事物并通知Router
        db.rollback()
        raise ValueError("请假不存在或已经审批")

    #更新成功后提交，再重新读取数据库中的最终状态
    db.commit()
    return db.get(StudentLeave,leave_id)

#请假记录必须存在
def cancel_leave(db: Session, leave_id: int, student_id: int):
    leave = db.get(StudentLeave, leave_id)
    if not leave:
        raise ValueError("请假记录不存在")
    #只能撤销当前登录学生自己的申请，防止修改URL中的ID操作他人请假记录
    if leave.student_id != student_id:
        raise ValueError("无权操作他人的请假记录")
    #已审批的记录属于最终状态，不允许学生删除
    if leave.status != LeaveStatus.PENDING.value:
        raise ValueError("已审批的申请不可撤销")
    #当前撤销采用“先查询、再删除”，与管理员并发之间仍有很小的竞争窗口
    #更严格的做法是使用带student_id和status='pending'条件的DELETE
    db.delete(leave)
    db.commit()
