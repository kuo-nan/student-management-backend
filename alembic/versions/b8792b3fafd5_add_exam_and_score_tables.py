"""create exam and score tables

Revision ID: b8792b3fafd5
Revises: 3f30721946d9
Create Date: 2026-11-03 19:28:10.885543
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8792b3fafd5"
down_revision: Union[str, Sequence[str], None] = "3f30721946d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exam",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("exam_time", sa.DateTime(), nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "exam_score",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("exam_score", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=True),
        sa.Column("update_time", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["course.id"]),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "exam_id",
            "student_id",
            "course_id",
            name="uk_exam_student_course",
        ),
    )


def downgrade() -> None:
    op.drop_table("exam_score")
    op.drop_table("exam")
