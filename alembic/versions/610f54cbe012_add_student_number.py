"""add unique student number

Revision ID: 610f54cbe012
Revises: d6e7f8a9b0c1
Create Date: 2026-11-08 15:18:20.932236
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op

revision: str = "610f54cbe012"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_student_student_no"


def _unique_student_number_exists(connection) -> bool:
    inspector = inspect(connection)
    constraints = inspector.get_unique_constraints("student")
    if any(item.get("column_names") == ["student_no"] for item in constraints):
        return True
    indexes = inspector.get_indexes("student")
    return any(
        item.get("unique") and item.get("column_names") == ["student_no"]
        for item in indexes
    )


def upgrade() -> None:
    connection = op.get_bind()
    columns = {
        column["name"] for column in inspect(connection).get_columns("student")
    }

    if "student_no" not in columns:
        op.add_column(
            "student",
            sa.Column("student_no", sa.Integer(), nullable=True),
        )

    null_count = connection.execute(
        text("SELECT COUNT(*) FROM student WHERE student_no IS NULL")
    ).scalar_one()
    duplicate_count = connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM (
                SELECT student_no
                FROM student
                GROUP BY student_no
                HAVING COUNT(*) > 1
            ) AS duplicated_student_numbers
            """
        )
    ).scalar_one()

    if null_count:
        raise RuntimeError("student.student_no 存在空值，请先补全旧数据")
    if duplicate_count:
        raise RuntimeError("student.student_no 存在重复值，请先修正旧数据")

    op.alter_column(
        "student",
        "student_no",
        existing_type=sa.Integer(),
        nullable=False,
    )

    if not _unique_student_number_exists(connection):
        op.create_unique_constraint(
            CONSTRAINT_NAME,
            "student",
            ["student_no"],
        )


def downgrade() -> None:
    connection = op.get_bind()
    if _unique_student_number_exists(connection):
        op.drop_constraint(CONSTRAINT_NAME, "student", type_="unique")

    columns = {
        column["name"] for column in inspect(connection).get_columns("student")
    }
    if "student_no" in columns:
        op.drop_column("student", "student_no")
