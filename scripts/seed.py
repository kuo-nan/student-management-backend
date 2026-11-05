import argparse
import os
import secrets

from sqlalchemy import select

from constants import UserRole
from database import SessionLocal
from models import Course, Dept, Student, User
from utils import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化本地演示数据")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", default=None)
    parser.add_argument("--reset-admin-password", action="store_true")
    args = parser.parse_args()

    admin_password = (
        args.admin_password
        or os.getenv("SEED_ADMIN_PASSWORD")
        or secrets.token_urlsafe(12)
    )

    with SessionLocal() as db:
        dept = db.scalar(select(Dept).where(Dept.dept_name == "计算机科学与技术"))
        if not dept:
            dept = Dept(dept_name="计算机科学与技术")
            db.add(dept)
            db.flush()

        course = db.scalar(select(Course).where(Course.course_name == "Python 后端开发"))
        if not course:
            course = Course(course_name="Python 后端开发", credits=3)
            db.add(course)
            db.flush()

        admin = db.scalar(select(User).where(User.username == args.admin_username))
        if not admin:
            admin = User(
                username=args.admin_username,
                password_hash=hash_password(admin_password),
                role=UserRole.ADMIN.value,
            )
            db.add(admin)
            print(f"已创建管理员：{args.admin_username}")
            print(f"管理员初始密码：{admin_password}")
        elif args.reset_admin_password:
            admin.password_hash = hash_password(admin_password)
            print(f"已重置管理员密码：{admin_password}")
        else:
            print(f"管理员已存在，跳过创建：{args.admin_username}")

        demo_user = db.scalar(select(User).where(User.username == "student"))
        if not demo_user:
            student = Student(
                name="张三",
                age=20,
                score=88,
                dept_id=dept.id,
            )
            demo_user = User(
                username="student",
                password_hash=hash_password("student12345"),
                role=UserRole.STUDENT.value,
                student=student,
            )
            db.add(demo_user)
            print("已创建演示学生账号：student / student12345")

        db.commit()


if __name__ == "__main__":
    main()
