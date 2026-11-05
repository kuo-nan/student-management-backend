from sqlalchemy import select
from sqlalchemy.orm import Session

from constants import LeaveStatus
from models import Student, StudentLeave
from schemas import LeaveAudit, LeaveCreate
from utils import paginate


def create_leaves(db: Session, student_id: int, data: LeaveCreate):
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
        status=LeaveStatus.PENDING.value,
    )
    db.add(db_leave)
    db.commit()
    db.refresh(db_leave)
    return db_leave


def get_my_leaves(
    db: Session,
    student_id: int,
    page: int,
    page_size: int,
):
    query = (
        select(StudentLeave)
        .where(StudentLeave.student_id == student_id)
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
    if status:
        query = query.where(StudentLeave.status == status)
    if student_id:
        query = query.where(StudentLeave.student_id == student_id)
    return paginate(db, query, page, page_size)


def audit_leave(db: Session, leave_id: int, data: LeaveAudit):
    leave = db.get(StudentLeave, leave_id)
    if not leave:
        raise ValueError("请假记录不存在")
    if leave.status != LeaveStatus.PENDING.value:
        raise ValueError("该请假已审批，不可重复操作")
    if data.status not in {
        LeaveStatus.APPROVED.value,
        LeaveStatus.REJECTED.value,
    }:
        raise ValueError("审批状态非法")

    leave.status = data.status
    leave.audit_remark = data.audit_remark
    db.commit()
    db.refresh(leave)
    return leave


def cancel_leave(db: Session, leave_id: int, student_id: int):
    leave = db.get(StudentLeave, leave_id)
    if not leave:
        raise ValueError("请假记录不存在")
    if leave.student_id != student_id:
        raise ValueError("无权操作他人的请假记录")
    if leave.status != LeaveStatus.PENDING.value:
        raise ValueError("已审批的申请不可撤销")
    db.delete(leave)
    db.commit()
