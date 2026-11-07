"""remove redundant primary key indexes

Revision ID: d6e7f8a9b0c1
Revises: c4d5e6f7a8b9
Create Date: 2026-11-07 10:00:00.000000
"""

from typing import Sequence, Union

from sqlalchemy import inspect

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REDUNDANT_INDEXES = (
    ("course", "ix_course_id"),
    ("dept", "ix_dept_id"),
    ("exam", "ix_exam_id"),
    ("operation_log", "ix_operation_log_id"),
    ("student", "ix_student_id"),
    ("teacher", "ix_teacher_id"),
    ("user", "ix_user_id"),
)


def _index_names(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    for table_name, index_name in REDUNDANT_INDEXES:
        if index_name in _index_names(table_name):
            op.drop_index(index_name, table_name=table_name)


def downgrade() -> None:
    for table_name, index_name in REDUNDANT_INDEXES:
        if index_name not in _index_names(table_name):
            op.create_index(index_name, table_name, ["id"], unique=False)
