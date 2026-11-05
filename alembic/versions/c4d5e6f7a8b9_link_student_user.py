"""link student identity and enforce exam name uniqueness

Revision ID: c4d5e6f7a8b9
Revises: b8792b3fafd5
Create Date: 2026-11-05 16:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b8792b3fafd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_student_user_id_user",
        "student",
        "user",
        ["user_id"],
        ["id"],
    )
    op.create_unique_constraint("uq_student_user_id", "student", ["user_id"])
    op.execute(
        """
        UPDATE exam AS target
        JOIN (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY name ORDER BY id) AS row_num
            FROM exam
        ) AS duplicated ON duplicated.id = target.id
        SET target.name = CONCAT(target.name, '#', target.id)
        WHERE duplicated.row_num > 1
        """
    )
    op.create_unique_constraint("uk_exam_name", "exam", ["name"])
    op.execute("UPDATE `user` SET `role` = 'student' WHERE `role` = 'user'")


def downgrade() -> None:
    op.execute("UPDATE `user` SET `role` = 'user' WHERE `role` = 'student'")
    op.drop_constraint("uk_exam_name", "exam", type_="unique")
    op.drop_constraint("uq_student_user_id", "student", type_="unique")
    op.drop_constraint("fk_student_user_id_user", "student", type_="foreignkey")
    op.drop_column("student", "user_id")
